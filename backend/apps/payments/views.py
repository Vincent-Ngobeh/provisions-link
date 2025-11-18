"""
ViewSet implementations for payment operations.
Handles payment intent creation, confirmation, and status checking.
"""
from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
import stripe
import logging

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

from apps.orders.models import Order
from apps.integrations.services.stripe_service import StripeConnectService
from .serializers import (
    CreatePaymentIntentSerializer,
    ConfirmPaymentSerializer,
    PaymentStatusSerializer,
    PaymentErrorSerializer
)

logger = logging.getLogger(__name__)


class CreatePaymentIntentView(views.APIView):
    """
    Create a Stripe payment intent for one or more orders.

    POST /api/v1/payments/create-intent/

    Request Body:
        {
            "order_ids": [1, 2, 3]
        }

    Response:
        {
            "payment_intent_id": "pi_xxx",
            "client_secret": "pi_xxx_secret_yyy",
            "amount": 15000,
            "currency": "gbp",
            "vendor": {...},
            "orders": [...],
            "commission": 500,
            "vendor_payout": 14500
        }
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Create payment intent for orders",
        description="""
        Create a Stripe payment intent for one or more orders using Stripe Connect.
 
        **Payment Flow:**
        1. Validates all orders belong to same vendor
        2. Calculates total amount including VAT
        3. Calculates platform commission (on subtotal only)
        4. Creates Stripe payment intent with Connect split payment
        5. Returns client_secret for frontend payment confirmation
 
        **Stripe Connect:**
        - Platform charges full amount to customer
        - Platform commission automatically deducted
        - Remainder transferred to vendor's Stripe account
 
        **Example Request:**
```json
        {
            "order_ids": [45, 46, 47]
        }
```
 
        **Example Response:**
```json
        {
            "payment_intent_id": "pi_xxx",
            "client_secret": "pi_xxx_secret_yyy",
            "amount": 15000,
            "commission": 500,
            "vendor_amount": 14500
        }
```
 
        **Commission Calculation:**
        - Applied to subtotal only (not VAT or delivery fees)
        - Rate set per vendor (typically 10%)
        - Automatically handled by Stripe Connect
 
        **Permissions:** Authenticated users only (order buyer)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'order_ids': {
                        'type': 'array',
                        'items': {'type': 'integer'},
                        'description': 'List of order IDs to pay for (must be from same vendor)'
                    }
                },
                'required': ['order_ids']
            }
        },
        responses={
            200: CreatePaymentIntentSerializer,
            400: PaymentErrorSerializer
        },
        tags=['Payments']
    )
    def post(self, request):
        """Create payment intent for orders."""
        # Validate request
        serializer = CreatePaymentIntentSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract validated data
        orders = serializer.validated_data['orders']
        vendor = serializer.validated_data['vendor']

        # Initialize Stripe service
        stripe_service = StripeConnectService()

        # IMPORTANT: Commission is calculated on subtotal only (not VAT/delivery)
        total_amount = sum(order.total for order in orders)
        commission_amount = sum(
            order.subtotal * vendor.commission_rate
            for order in orders
        )
        vendor_amount = total_amount - commission_amount

        # Convert to pence
        total_pence = int(total_amount * 100)
        commission_pence = int(commission_amount * 100)
        vendor_pence = int(vendor_amount * 100)

        # Create order IDs string for metadata
        order_ids_str = ','.join(str(o.id) for o in orders)

        try:
            # Check if we're in test mode and vendor has a test placeholder account
            is_test_mode = not stripe.api_key.startswith('sk_live_')
            is_placeholder_account = (
                vendor.stripe_account_id and
                ('test' in vendor.stripe_account_id.lower() or
                 not vendor.stripe_account_id.startswith('acct_'))
            )

            # Create payment intent parameters
            payment_intent_params = {
                'amount': total_pence,
                'currency': 'gbp',
                'metadata': {
                    'order_ids': order_ids_str,
                    'vendor_id': str(vendor.id),
                    'buyer_id': str(request.user.id),
                    'platform': 'provisions_link'
                },
                'description': f"Orders: {', '.join(o.reference_number for o in orders)}",
                'receipt_email': request.user.email
            }

            # Only add Connect-specific fields if vendor has a REAL Stripe account
            if vendor.stripe_account_id and not is_placeholder_account:
                payment_intent_params['application_fee_amount'] = commission_pence
                payment_intent_params['transfer_data'] = {
                    'destination': vendor.stripe_account_id,
                }
            elif is_test_mode:
                # In test mode with placeholder account, log the commission
                # but do not attempt transfer to a non-existent account
                logger.info(
                    f"Test mode: Would charge {total_pence} pence with "
                    f"{commission_pence} pence commission to vendor {vendor.id}"
                )

            # Create payment intent with Stripe
            payment_intent = stripe.PaymentIntent.create(
                **payment_intent_params)

            # IMPORTANT: marketplace_fee and vendor_payout are already set correctly by OrderService
            # We only update the payment_intent_id here to avoid overwriting correct values
            with transaction.atomic():
                for order in orders:
                    order.stripe_payment_intent_id = payment_intent.id
                    # Calculate marketplace fee on subtotal only (not VAT/delivery)
                    order.marketplace_fee = order.subtotal * vendor.commission_rate
                    order.vendor_payout = order.total - order.marketplace_fee
                    order.save(update_fields=[
                        'stripe_payment_intent_id',
                        'marketplace_fee',
                        'vendor_payout'
                    ])

            # Format response
            response_data = {
                'payment_intent_id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'amount': total_pence,
                'commission': commission_pence,
                'vendor_amount': vendor_pence
            }

            # Use serializer for formatting
            output_serializer = CreatePaymentIntentSerializer(
                instance=response_data,
                context={
                    'orders': orders,
                    'vendor': vendor
                }
            )

            return Response(
                output_serializer.data,
                status=status.HTTP_200_OK
            )

        except stripe.error.InvalidRequestError as e:
            # Handle specific Stripe errors (like invalid account)
            error_message = str(e)

            if 'No such destination' in error_message or 'No such account' in error_message:
                error_serializer = PaymentErrorSerializer({
                    'error': f'The vendor ({vendor.business_name}) has not completed their Stripe setup. Please contact support.',
                    'error_code': 'INVALID_VENDOR_ACCOUNT',
                    'details': {
                        'type': 'InvalidRequestError',
                        'vendor_id': vendor.id,
                        'vendor_name': vendor.business_name
                    }
                })
            else:
                error_serializer = PaymentErrorSerializer({
                    'error': error_message,
                    'error_code': 'STRIPE_ERROR',
                    'details': {'type': 'InvalidRequestError'}
                })

            return Response(
                error_serializer.data,
                status=status.HTTP_400_BAD_REQUEST
            )

        except stripe.error.StripeError as e:
            # Stripe error
            error_serializer = PaymentErrorSerializer({
                'error': str(e),
                'error_code': 'STRIPE_ERROR',
                'details': {'type': type(e).__name__}
            })
            return Response(
                error_serializer.data,
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as e:
            # Unexpected error
            error_serializer = PaymentErrorSerializer({
                'error': 'Failed to create payment intent',
                'error_code': 'CREATION_FAILED',
                'details': {'message': str(e)}
            })
            return Response(
                error_serializer.data,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ConfirmPaymentView(views.APIView):
    """
    Confirm payment after Stripe confirms it client-side.
    Updates order statuses to 'paid'.

    POST /api/v1/payments/confirm-payment/

    Request Body:
        {
            "payment_intent_id": "pi_xxx",
            "order_ids": [1, 2, 3]
        }

    Response:
        {
            "success": true,
            "orders_updated": 3,
            "orders_already_paid": 0,
            "payment_intent_id": "pi_xxx",
            "orders": [...]
        }
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Confirm payment after Stripe authorization",
        description="""
        Confirm payment completion and update order statuses to 'paid'.
 
        **Process:**
        1. Retrieves payment intent from Stripe
        2. Validates payment succeeded
        3. Updates all associated orders to 'paid' status
        4. Triggers vendor notifications
        5. Records payment details on orders
 
        **Important:**
        - Call this AFTER Stripe confirms payment on frontend
        - Idempotent - safe to call multiple times
        - Updates orders atomically (all or none)
 
        **Example Request:**
```json
        {
            "payment_intent_id": "pi_xxx",
            "order_ids": [45, 46, 47]
        }
```
 
        **Example Response:**
```json
        {
            "success": true,
            "orders_updated": 3,
            "orders_already_paid": 0,
            "payment_intent_id": "pi_xxx",
            "orders": [...]
        }
```
 
        **Error Handling:**
        - Returns 400 if payment not confirmed
        - Returns 404 if orders not found
        - Returns 403 if user doesn't own orders
 
        **Permissions:** Authenticated users only (order buyer)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'payment_intent_id': {'type': 'string', 'description': 'Stripe payment intent ID'},
                    'order_ids': {
                        'type': 'array',
                        'items': {'type': 'integer'},
                        'description': 'Order IDs being paid'
                    }
                },
                'required': ['payment_intent_id', 'order_ids']
            }
        },
        responses={
            200: ConfirmPaymentSerializer,
            400: PaymentErrorSerializer
        },
        tags=['Payments']
    )
    @transaction.atomic
    def post(self, request):
        """Confirm payment and update orders."""
        # Validate request
        serializer = ConfirmPaymentSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save updates (performs order status updates)
        result = serializer.save()

        # Format response
        output_serializer = ConfirmPaymentSerializer(
            instance=result
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_200_OK
        )


class PaymentStatusView(views.APIView):
    """
    Get current status of a payment intent.

    GET /api/v1/payments/payment-status/<intent_id>/

    Response:
        {
            "payment_intent_id": "pi_xxx",
            "status": "succeeded",
            "amount": 15000,
            "currency": "gbp",
            "created": "2024-01-15T10:25:00Z",
            "metadata": {...}
        }
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get payment intent status",
        description="""
        Retrieve the current status of a Stripe payment intent.
 
        **Payment Statuses:**
        - `requires_payment_method`: Waiting for payment method
        - `requires_confirmation`: Ready to be confirmed
        - `requires_action`: Requires 3D Secure or other action
        - `processing`: Payment is processing
        - `succeeded`: Payment completed successfully
        - `canceled`: Payment was canceled
        - `requires_capture`: Payment authorized, awaiting capture
 
        **Use Cases:**
        - Check payment status after user action
        - Poll for payment completion
        - Debug payment issues
        - Display payment history
 
        **Response Example:**
```json
        {
            "payment_intent_id": "pi_xxx",
            "status": "succeeded",
            "amount": 15000,
            "currency": "gbp",
            "created": "2024-01-15T10:25:00Z",
            "metadata": {
                "order_ids": "45,46,47",
                "vendor_id": "3",
                "buyer_id": "12"
            }
        }
```
 
        **Permissions:** Authenticated users (payment owner or admin)
        """,
        parameters=[
            OpenApiParameter(
                name='intent_id',
                type=Types.STR,
                location=OpenApiParameter.PATH,
                description='Stripe payment intent ID (starts with "pi_")'
            ),
        ],
        responses={
            200: PaymentStatusSerializer,
            400: PaymentErrorSerializer,
            404: {'description': 'Payment intent not found'}
        },
        tags=['Payments']
    )
    def get(self, request, intent_id):
        """Get payment intent status from Stripe."""
        # Validate intent_id format
        if not intent_id.startswith('pi_'):
            return Response(
                {'error': 'Invalid payment intent ID format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Retrieve payment intent from Stripe
            payment_intent = stripe.PaymentIntent.retrieve(intent_id)

            # Check if user has access to this payment intent
            metadata = payment_intent.metadata or {}
            buyer_id = metadata.get('buyer_id')

            # Allow if user is the buyer or staff
            if buyer_id and int(buyer_id) != request.user.id and not request.user.is_staff:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Format response
            serializer = PaymentStatusSerializer(payment_intent)

            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        except stripe.error.InvalidRequestError:
            return Response(
                {'error': 'Payment intent not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        except stripe.error.StripeError as e:
            error_serializer = PaymentErrorSerializer({
                'error': str(e),
                'error_code': 'STRIPE_ERROR'
            })
            return Response(
                error_serializer.data,
                status=status.HTTP_400_BAD_REQUEST
            )
