"""
Serializers for payment operations.
Handles validation and formatting for payment requests and responses.
"""
from rest_framework import serializers
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order
from apps.vendors.models import Vendor


class CreatePaymentIntentSerializer(serializers.Serializer):
    """
    Serializer for creating a Stripe payment intent.

    Takes a list of order IDs and validates:
    - All orders exist and belong to the requesting user
    - All orders are in 'pending' status
    - All orders belong to the same vendor
    - Vendor is ready to accept payments
    """
    order_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=50,
        help_text="List of order IDs to pay for"
    )

    def validate_order_ids(self, value):
        """
        Validate that all order IDs exist and belong to the requesting user.
        """
        # Remove duplicates
        order_ids = list(set(value))

        if not order_ids:
            raise serializers.ValidationError(
                "At least one order ID is required")

        # Get user from context
        user = self.context['request'].user

        # Fetch all orders
        orders = Order.objects.filter(
            id__in=order_ids,
            buyer=user
        ).select_related('vendor')

        # Check all orders exist
        if orders.count() != len(order_ids):
            found_ids = set(orders.values_list('id', flat=True))
            missing_ids = set(order_ids) - found_ids
            raise serializers.ValidationError(
                f"Orders not found or don't belong to you: {missing_ids}"
            )

        # Store orders for later use
        self._orders = list(orders)

        return order_ids

    def validate(self, attrs):
        """
        Validate that all orders are valid for payment.
        """
        orders = self._orders

        # Check all orders are pending
        non_pending = [o for o in orders if o.status != 'pending']
        if non_pending:
            order_refs = [o.reference_number for o in non_pending]
            raise serializers.ValidationError({
                'order_ids': f"Orders must be in 'pending' status. Invalid orders: {order_refs}"
            })

        # Check all orders belong to same vendor
        vendors = set(o.vendor_id for o in orders)
        if len(vendors) > 1:
            raise serializers.ValidationError({
                'order_ids': "All orders must belong to the same vendor"
            })

        # Check vendor is ready to accept payments
        vendor = orders[0].vendor
        if not vendor.stripe_account_id or not vendor.stripe_onboarding_complete:
            raise serializers.ValidationError({
                'vendor': f"Vendor {vendor.business_name} is not ready to accept payments"
            })

        # Store vendor for response
        attrs['orders'] = orders
        attrs['vendor'] = vendor

        return attrs

    def to_representation(self, instance):
        """
        Format the payment intent response.

        Args:
            instance: Dict containing payment_intent_id, client_secret, etc.

        Returns:
            Formatted response with payment details
        """
        orders = self.context.get('orders', [])
        vendor = self.context.get('vendor')

        return {
            'payment_intent_id': instance.get('payment_intent_id'),
            'client_secret': instance.get('client_secret'),
            'amount': instance.get('amount'),  # in pence
            'currency': 'gbp',
            'vendor': {
                'id': vendor.id,
                'name': vendor.business_name,
                'stripe_account_id': vendor.stripe_account_id
            },
            'orders': [
                {
                    'id': order.id,
                    'reference': order.reference_number,
                    'total': str(order.total)
                }
                for order in orders
            ],
            'commission': instance.get('commission'),  # in pence
            'vendor_payout': instance.get('vendor_amount')  # in pence
        }


class ConfirmPaymentSerializer(serializers.Serializer):
    """
    Serializer for confirming a payment after Stripe confirms it client-side.

    Updates order statuses and records payment timestamp.
    """
    payment_intent_id = serializers.CharField(
        max_length=200,
        help_text="Stripe payment intent ID"
    )
    order_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        max_length=50,
        help_text="List of order IDs that were paid"
    )

    def validate_payment_intent_id(self, value):
        """Validate payment intent ID format."""
        if not value.startswith('pi_'):
            raise serializers.ValidationError(
                "Invalid payment intent ID format"
            )
        return value

    def validate_order_ids(self, value):
        """Validate orders exist and belong to user."""
        # Remove duplicates
        order_ids = list(set(value))

        user = self.context['request'].user

        # Fetch orders
        orders = Order.objects.filter(
            id__in=order_ids,
            buyer=user
        ).select_for_update()  # Lock for update

        # Check all exist
        if orders.count() != len(order_ids):
            raise serializers.ValidationError(
                "One or more orders not found or don't belong to you"
            )

        # Store for validation
        self._orders = list(orders)

        return order_ids

    def validate(self, attrs):
        """
        Validate payment intent matches orders.
        """
        orders = self._orders
        payment_intent_id = attrs['payment_intent_id']

        # Check if orders are already paid
        already_paid = [o for o in orders if o.status == 'paid']
        if already_paid:
            # This is okay - idempotent operation
            # But we'll skip updating them
            attrs['already_paid'] = [o.id for o in already_paid]
            attrs['to_update'] = [o for o in orders if o.status != 'paid']
        else:
            attrs['already_paid'] = []
            attrs['to_update'] = orders

        # Verify payment intent matches at least one order
        # (In real implementation, you'd fetch from Stripe to verify)
        order_with_intent = any(
            o.stripe_payment_intent_id == payment_intent_id
            for o in orders
        )

        if not order_with_intent:
            # Check if any order has no payment intent (first payment)
            orders_without_intent = [
                o for o in orders
                if not o.stripe_payment_intent_id
            ]
            if orders_without_intent:
                # Assign payment intent to these orders
                attrs['assign_intent'] = True
            else:
                raise serializers.ValidationError({
                    'payment_intent_id': "Payment intent doesn't match any of the provided orders"
                })

        attrs['orders'] = orders
        return attrs

    @transaction.atomic
    def save(self):
        """
        Update order statuses to 'paid'.

        Returns:
            Dict with update statistics and order details
        """
        orders_to_update = self.validated_data.get('to_update', [])
        already_paid_ids = self.validated_data.get('already_paid', [])
        payment_intent_id = self.validated_data['payment_intent_id']
        should_assign_intent = self.validated_data.get('assign_intent', False)

        updated_orders = []
        now = timezone.now()

        for order in orders_to_update:
            # Assign payment intent if needed
            if should_assign_intent or not order.stripe_payment_intent_id:
                order.stripe_payment_intent_id = payment_intent_id

            # Update status
            order.status = 'paid'
            order.paid_at = now
            order.save(update_fields=[
                       'status', 'paid_at', 'stripe_payment_intent_id'])

            updated_orders.append(order)

        return {
            'success': True,
            'orders_updated': len(updated_orders),
            'orders_already_paid': len(already_paid_ids),
            'orders': updated_orders,
            'payment_intent_id': payment_intent_id
        }

    def to_representation(self, instance):
        """Format the confirmation response."""
        from apps.orders.serializers import OrderListSerializer

        return {
            'success': instance['success'],
            'orders_updated': instance['orders_updated'],
            'orders_already_paid': instance['orders_already_paid'],
            'payment_intent_id': instance['payment_intent_id'],
            'orders': OrderListSerializer(instance['orders'], many=True).data
        }


class PaymentStatusSerializer(serializers.Serializer):
    """
    Serializer for payment status responses.
    Formats Stripe payment intent data for frontend.
    """
    payment_intent_id = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.IntegerField(help_text="Amount in pence")
    currency = serializers.CharField()
    created = serializers.DateTimeField()
    metadata = serializers.DictField(required=False)

    def to_representation(self, instance):
        """
        Format payment status response.

        Args:
            instance: Stripe PaymentIntent object or dict
        """
        # Handle both Stripe objects and dicts
        if hasattr(instance, 'id'):
            # Stripe object
            return {
                'payment_intent_id': instance.id,
                'status': instance.status,
                'amount': instance.amount,
                'currency': instance.currency,
                'created': timezone.datetime.fromtimestamp(instance.created),
                'metadata': dict(instance.metadata) if instance.metadata else {},
                'payment_method': instance.payment_method if hasattr(instance, 'payment_method') else None,
                'next_action': instance.next_action if hasattr(instance, 'next_action') else None
            }
        else:
            # Dict (from our service layer)
            return {
                'payment_intent_id': instance.get('payment_intent_id'),
                'status': instance.get('status'),
                'amount': instance.get('amount'),
                'currency': instance.get('currency', 'gbp'),
                'created': instance.get('created'),
                'metadata': instance.get('metadata', {}),
                'payment_method': instance.get('payment_method'),
                'next_action': instance.get('next_action')
            }


class PaymentErrorSerializer(serializers.Serializer):
    """
    Serializer for payment error responses.
    Provides consistent error format across payment endpoints.
    """
    error = serializers.CharField(help_text="Error message")
    error_code = serializers.CharField(
        required=False,
        help_text="Machine-readable error code"
    )
    details = serializers.DictField(
        required=False,
        help_text="Additional error details"
    )

    def to_representation(self, instance):
        """
        Format error response.

        Args:
            instance: Error dict or ServiceResult
        """
        if hasattr(instance, 'error'):
            # ServiceResult object
            return {
                'error': instance.error,
                'error_code': getattr(instance, 'error_code', None),
                'details': getattr(instance, 'details', {})
            }
        else:
            # Dict
            return {
                'error': instance.get('error'),
                'error_code': instance.get('error_code'),
                'details': instance.get('details', {})
            }
