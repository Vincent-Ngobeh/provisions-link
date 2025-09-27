"""
Stripe Connect integration service for marketplace payments.
Handles vendor onboarding, payment processing, and automated commission splits.
"""
import stripe
from typing import Optional, Dict, Any, List
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.services.base import (
    BaseService, ExternalServiceError, ServiceResult, ValidationError
)
from apps.vendors.models import Vendor
from apps.orders.models import Order, OrderItem
from apps.buying_groups.models import GroupCommitment


class StripeConnectService(BaseService):
    """
    Service for managing Stripe Connect operations.
    Handles vendor accounts, payment processing, and marketplace splits.

    Stripe Connect Documentation: https://stripe.com/docs/connect
    """

    # Stripe configuration
    PLATFORM_FEE_PERCENT = Decimal('2.9')  # Stripe's fee
    PLATFORM_FEE_FIXED = Decimal('0.30')   # Fixed fee in GBP

    # Account types
    ACCOUNT_TYPE = 'express'  # Using Express accounts

    def __init__(self):
        """Initialize Stripe service with API key."""
        super().__init__()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.platform_account_id = settings.STRIPE_PLATFORM_ACCOUNT_ID

    def create_vendor_account(self, vendor: Vendor) -> ServiceResult:
        """
        Create a Stripe Express account for a vendor.

        Args:
            vendor: Vendor instance

        Returns:
            ServiceResult containing account creation details or error
        """
        try:
            # Check if vendor already has an account
            if vendor.stripe_account_id:
                return ServiceResult.fail(
                    "Vendor already has a Stripe account",
                    error_code="ACCOUNT_EXISTS"
                )

            # Create Express account
            account = stripe.Account.create(
                type=self.ACCOUNT_TYPE,
                country='GB',
                email=vendor.user.email,
                capabilities={
                    'card_payments': {'requested': True},
                    'transfers': {'requested': True}
                },
                business_type='company',
                company={
                    'name': vendor.business_name,
                    'phone': vendor.phone_number or None,
                    'address': {
                        'line1': 'To be updated',  # Will be updated during onboarding
                        'postal_code': vendor.postcode,
                        'city': 'London',  # Placeholder
                        'country': 'GB'
                    }
                },
                business_profile={
                    'name': vendor.business_name,
                    'product_description': vendor.description[:500] if vendor.description else None,
                    'mcc': '5499',  # Misc Food Stores - Default
                    'url': None  # Will be added if vendor has website
                },
                settings={
                    'payouts': {
                        'schedule': {
                            'interval': 'weekly',
                            'weekly_anchor': 'friday'
                        }
                    }
                },
                metadata={
                    'vendor_id': str(vendor.id),
                    'platform': 'provisions_link'
                }
            )

            # Save account ID
            vendor.stripe_account_id = account.id
            vendor.save(update_fields=['stripe_account_id'])

            self.log_info(
                f"Created Stripe account for vendor {vendor.id}",
                vendor_id=vendor.id,
                account_id=account.id
            )

            # Generate onboarding link
            onboarding_result = self.generate_onboarding_link(vendor)

            if not onboarding_result.success:
                return onboarding_result

            return ServiceResult.ok({
                'account_id': account.id,
                'onboarding_url': onboarding_result.data['url']
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error creating vendor account",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                f"Failed to create Stripe account: {str(e)}",
                error_code="STRIPE_ERROR"
            )
        except Exception as e:
            self.log_error(
                f"Error creating vendor account",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                "Failed to create vendor account",
                error_code="CREATION_FAILED"
            )

    def generate_onboarding_link(self, vendor: Vendor) -> ServiceResult:
        """
        Generate Stripe Connect onboarding link for vendor.

        Args:
            vendor: Vendor instance

        Returns:
            ServiceResult containing onboarding URL or error
        """
        try:
            if not vendor.stripe_account_id:
                return ServiceResult.fail(
                    "Vendor does not have a Stripe account",
                    error_code="NO_ACCOUNT"
                )

            # Create account link
            account_link = stripe.AccountLink.create(
                account=vendor.stripe_account_id,
                refresh_url=f"{settings.FRONTEND_URL}/vendor/stripe/refresh",
                return_url=f"{settings.FRONTEND_URL}/vendor/stripe/complete",
                type='account_onboarding'
            )

            self.log_info(
                f"Generated onboarding link for vendor {vendor.id}",
                vendor_id=vendor.id
            )

            return ServiceResult.ok({
                'url': account_link.url,
                'expires_at': datetime.fromtimestamp(account_link.expires_at)
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error generating onboarding link",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                f"Failed to generate onboarding link: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def check_account_status(self, vendor: Vendor) -> ServiceResult:
        """
        Check if vendor's Stripe account is fully onboarded.

        Args:
            vendor: Vendor instance

        Returns:
            ServiceResult containing account status or error
        """
        try:
            if not vendor.stripe_account_id:
                return ServiceResult.ok({
                    'status': 'not_created',
                    'charges_enabled': False,
                    'payouts_enabled': False
                })

            account = stripe.Account.retrieve(vendor.stripe_account_id)

            # Update vendor status if changed
            if account.charges_enabled != vendor.stripe_onboarding_complete:
                vendor.stripe_onboarding_complete = account.charges_enabled
                vendor.save(update_fields=['stripe_onboarding_complete'])

            return ServiceResult.ok({
                'status': 'active' if account.charges_enabled else 'pending',
                'charges_enabled': account.charges_enabled,
                'payouts_enabled': account.payouts_enabled,
                'requirements': account.requirements.currently_due if hasattr(account, 'requirements') else []
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error checking account status",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                f"Failed to check account status: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def process_marketplace_order(self, order: Order) -> ServiceResult:
        """
        Process payment for an order with automatic vendor split.

        Args:
            order: Order instance

        Returns:
            ServiceResult containing payment intent or error
        """
        try:
            # Validate order
            if order.status != 'pending':
                return ServiceResult.fail(
                    "Order is not in pending status",
                    error_code="INVALID_STATUS"
                )

            vendor = order.vendor

            # Check vendor account status
            if not vendor.stripe_account_id or not vendor.stripe_onboarding_complete:
                return ServiceResult.fail(
                    "Vendor Stripe account not ready",
                    error_code="VENDOR_NOT_READY"
                )

            # Calculate amounts (in pence)
            total_pence = int(order.total * 100)
            commission_pence = int(order.total * vendor.commission_rate * 100)
            vendor_amount_pence = total_pence - commission_pence

            # Create payment intent with automatic transfer
            payment_intent = stripe.PaymentIntent.create(
                amount=total_pence,
                currency='gbp',
                application_fee_amount=commission_pence,
                transfer_data={
                    'destination': vendor.stripe_account_id,
                },
                metadata={
                    'order_id': str(order.id),
                    'order_reference': order.reference_number,
                    'vendor_id': str(vendor.id),
                    'platform': 'provisions_link'
                },
                description=f"Order {order.reference_number}",
                receipt_email=order.buyer.email
            )

            # Update order with payment details
            order.stripe_payment_intent_id = payment_intent.id
            order.marketplace_fee = Decimal(commission_pence) / 100
            order.vendor_payout = Decimal(vendor_amount_pence) / 100
            order.save(update_fields=[
                'stripe_payment_intent_id',
                'marketplace_fee',
                'vendor_payout'
            ])

            self.log_info(
                f"Created payment intent for order {order.id}",
                order_id=order.id,
                payment_intent_id=payment_intent.id,
                amount=total_pence
            )

            return ServiceResult.ok({
                'payment_intent_id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'amount': total_pence,
                'commission': commission_pence,
                'vendor_amount': vendor_amount_pence
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error processing order payment",
                exception=e,
                order_id=order.id
            )
            return ServiceResult.fail(
                f"Payment processing failed: {str(e)}",
                error_code="PAYMENT_FAILED"
            )
        except Exception as e:
            self.log_error(
                f"Error processing order payment",
                exception=e,
                order_id=order.id
            )
            return ServiceResult.fail(
                "Payment processing failed",
                error_code="PROCESSING_FAILED"
            )

    def create_payment_intent_for_group(
        self,
        amount: Decimal,
        group_id: int,
        buyer_id: int
    ) -> ServiceResult:
        """
        Create a payment intent for group buying (pre-authorization).

        Args:
            amount: Total amount including VAT
            group_id: BuyingGroup ID
            buyer_id: Buyer user ID

        Returns:
            ServiceResult containing payment intent details or error
        """
        try:
            amount_pence = int(amount * 100)

            # Create payment intent with manual capture
            payment_intent = stripe.PaymentIntent.create(
                amount=amount_pence,
                currency='gbp',
                capture_method='manual',  # Important: Don't charge immediately
                metadata={
                    'type': 'group_buying',
                    'group_id': str(group_id),
                    'buyer_id': str(buyer_id),
                    'platform': 'provisions_link'
                },
                description=f"Group buying commitment - Group {group_id}"
            )

            self.log_info(
                f"Created group buying payment intent",
                group_id=group_id,
                buyer_id=buyer_id,
                payment_intent_id=payment_intent.id
            )

            return ServiceResult.ok({
                'intent_id': payment_intent.id,
                'client_secret': payment_intent.client_secret,
                'amount': amount_pence
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error creating group payment intent",
                exception=e,
                group_id=group_id
            )
            return ServiceResult.fail(
                f"Failed to create payment intent: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def capture_group_payment(self, payment_intent_id: str) -> ServiceResult:
        """
        Capture a pre-authorized payment for successful group buy.

        Args:
            payment_intent_id: Stripe payment intent ID

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            payment_intent = stripe.PaymentIntent.capture(payment_intent_id)

            self.log_info(
                f"Captured payment intent {payment_intent_id}",
                payment_intent_id=payment_intent_id,
                amount=payment_intent.amount
            )

            return ServiceResult.ok({
                'captured': True,
                'amount': payment_intent.amount,
                'status': payment_intent.status
            })

        except stripe.error.InvalidRequestError as e:
            if 'already been captured' in str(e):
                return ServiceResult.ok({
                    'captured': True,
                    'message': 'Already captured'
                })

            self.log_error(
                f"Invalid request capturing payment",
                exception=e,
                payment_intent_id=payment_intent_id
            )
            return ServiceResult.fail(
                f"Failed to capture payment: {str(e)}",
                error_code="CAPTURE_FAILED"
            )
        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error capturing payment",
                exception=e,
                payment_intent_id=payment_intent_id
            )
            return ServiceResult.fail(
                f"Failed to capture payment: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def cancel_payment_intent(self, payment_intent_id: str) -> ServiceResult:
        """
        Cancel a payment intent (for failed groups or cancelled commitments).

        Args:
            payment_intent_id: Stripe payment intent ID

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            payment_intent = stripe.PaymentIntent.cancel(payment_intent_id)

            self.log_info(
                f"Cancelled payment intent {payment_intent_id}",
                payment_intent_id=payment_intent_id
            )

            return ServiceResult.ok({
                'cancelled': True,
                'status': payment_intent.status
            })

        except stripe.error.InvalidRequestError as e:
            if 'already been canceled' in str(e):
                return ServiceResult.ok({
                    'cancelled': True,
                    'message': 'Already cancelled'
                })

            self.log_error(
                f"Invalid request cancelling payment",
                exception=e,
                payment_intent_id=payment_intent_id
            )
            return ServiceResult.fail(
                f"Failed to cancel payment: {str(e)}",
                error_code="CANCEL_FAILED"
            )
        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error cancelling payment",
                exception=e,
                payment_intent_id=payment_intent_id
            )
            return ServiceResult.fail(
                f"Failed to cancel payment: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def process_refund(
        self,
        order_id: int,
        amount: Optional[Decimal] = None,
        reason: str = 'requested_by_customer'
    ) -> ServiceResult:
        """
        Process a refund for an order.

        Args:
            order_id: Order ID
            amount: Amount to refund (None for full refund)
            reason: Refund reason for Stripe

        Returns:
            ServiceResult containing refund details or error
        """
        try:
            order = Order.objects.get(id=order_id)

            if not order.stripe_payment_intent_id:
                return ServiceResult.fail(
                    "Order has no payment to refund",
                    error_code="NO_PAYMENT"
                )

            if order.status not in ['paid', 'processing', 'delivered']:
                return ServiceResult.fail(
                    f"Cannot refund order with status {order.status}",
                    error_code="INVALID_STATUS"
                )

            # Calculate refund amount
            if amount is None:
                refund_amount_pence = int(order.total * 100)
            else:
                refund_amount_pence = int(amount * 100)

                # Validate amount
                if refund_amount_pence > int(order.total * 100):
                    return ServiceResult.fail(
                        "Refund amount exceeds order total",
                        error_code="AMOUNT_TOO_HIGH"
                    )

            # Create refund
            refund = stripe.Refund.create(
                payment_intent=order.stripe_payment_intent_id,
                amount=refund_amount_pence,
                reason=reason,
                metadata={
                    'order_id': str(order.id),
                    'order_reference': order.reference_number
                }
            )

            # Update order status
            if refund_amount_pence == int(order.total * 100):
                order.status = 'refunded'
                order.save(update_fields=['status'])

            self.log_info(
                f"Processed refund for order {order.id}",
                order_id=order.id,
                refund_id=refund.id,
                amount=refund_amount_pence
            )

            return ServiceResult.ok({
                'refund_id': refund.id,
                'amount': refund_amount_pence,
                'status': refund.status,
                'created': datetime.fromtimestamp(refund.created)
            })

        except Order.DoesNotExist:
            return ServiceResult.fail(
                f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND"
            )
        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error processing refund",
                exception=e,
                order_id=order_id
            )
            return ServiceResult.fail(
                f"Refund failed: {str(e)}",
                error_code="REFUND_FAILED"
            )

    def create_payout(
        self,
        vendor_id: int,
        amount: Decimal,
        description: str = "Manual payout"
    ) -> ServiceResult:
        """
        Create a manual payout to vendor (usually automatic).

        Args:
            vendor_id: Vendor ID
            amount: Payout amount in GBP
            description: Payout description

        Returns:
            ServiceResult containing payout details or error
        """
        try:
            vendor = Vendor.objects.get(id=vendor_id)

            if not vendor.stripe_account_id:
                return ServiceResult.fail(
                    "Vendor has no Stripe account",
                    error_code="NO_ACCOUNT"
                )

            amount_pence = int(amount * 100)

            # Create payout on connected account
            payout = stripe.Payout.create(
                amount=amount_pence,
                currency='gbp',
                description=description,
                metadata={
                    'vendor_id': str(vendor_id),
                    'type': 'manual'
                },
                stripe_account=vendor.stripe_account_id
            )

            self.log_info(
                f"Created payout for vendor {vendor_id}",
                vendor_id=vendor_id,
                payout_id=payout.id,
                amount=amount_pence
            )

            return ServiceResult.ok({
                'payout_id': payout.id,
                'amount': amount_pence,
                'arrival_date': datetime.fromtimestamp(payout.arrival_date),
                'status': payout.status
            })

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error creating payout",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                f"Payout failed: {str(e)}",
                error_code="PAYOUT_FAILED"
            )

    def get_vendor_balance(self, vendor: Vendor) -> ServiceResult:
        """
        Get vendor's current Stripe balance.

        Args:
            vendor: Vendor instance

        Returns:
            ServiceResult containing balance information or error
        """
        try:
            if not vendor.stripe_account_id:
                return ServiceResult.fail(
                    "Vendor has no Stripe account",
                    error_code="NO_ACCOUNT"
                )

            # Get balance from connected account
            balance = stripe.Balance.retrieve(
                stripe_account=vendor.stripe_account_id
            )

            # Format balance data
            available = sum(b['amount'] for b in balance.available)
            pending = sum(b['amount'] for b in balance.pending)

            return ServiceResult.ok({
                'available': available / 100,  # Convert pence to pounds
                'pending': pending / 100,
                'currency': 'GBP'
            })

        except stripe.error.StripeError as e:
            self.log_error(
                f"Stripe error fetching balance",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                f"Failed to fetch balance: {str(e)}",
                error_code="STRIPE_ERROR"
            )

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> ServiceResult:
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw request body
            signature: Stripe signature header

        Returns:
            ServiceResult containing event or error
        """
        try:
            event = stripe.Webhook.construct_event(
                payload,
                signature,
                self.webhook_secret
            )

            return ServiceResult.ok(event)

        except ValueError:
            self.log_error("Invalid webhook payload")
            return ServiceResult.fail(
                "Invalid payload",
                error_code="INVALID_PAYLOAD"
            )
        except stripe.error.SignatureVerificationError:
            self.log_error("Invalid webhook signature")
            return ServiceResult.fail(
                "Invalid signature",
                error_code="INVALID_SIGNATURE"
            )
