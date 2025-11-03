"""
Stripe webhook event handler service.
Processes different webhook events with specific handlers for each event type.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist

from apps.core.services.base import BaseService, ServiceResult
from apps.orders.models import Order
from apps.vendors.models import Vendor
from apps.buying_groups.models import GroupCommitment

logger = logging.getLogger(__name__)


class StripeWebhookHandler(BaseService):
    """
    Handles Stripe webhook events with event-specific methods.
    Uses a handler registry pattern for clean event routing.

    Supported Events:
    - payment_intent.succeeded: Mark orders as paid
    - payment_intent.payment_failed: Log payment failures
    - account.updated: Update vendor Stripe status
    - payout.paid: Track vendor payouts
    - charge.refunded: Handle refunds
    """

    def __init__(self):
        """Initialize handler with event registry."""
        super().__init__()

        # Event handler registry
        self.handlers = {
            'payment_intent.succeeded': self.handle_payment_intent_succeeded,
            'payment_intent.payment_failed': self.handle_payment_intent_failed,
            'account.updated': self.handle_account_updated,
            'payout.paid': self.handle_payout_paid,
            'charge.refunded': self.handle_charge_refunded,
            'payment_intent.canceled': self.handle_payment_intent_canceled,
        }

    def handle_event(self, event: Dict[str, Any]) -> ServiceResult:
        """
        Main entry point for webhook events.
        Routes events to specific handlers based on event type.

        Args:
            event: Stripe event object (dict)

        Returns:
            ServiceResult indicating success or failure
        """
        event_type = event.get('type')
        event_id = event.get('id')

        self.log_info(
            f"Processing webhook event: {event_type}",
            event_id=event_id,
            event_type=event_type
        )

        # Get handler for this event type
        handler = self.handlers.get(event_type)

        if not handler:
            # Unknown event type - log but don't error
            self.log_info(
                f"Unhandled webhook event type: {event_type}",
                event_id=event_id
            )
            return ServiceResult.ok({
                'message': f'Event type {event_type} not handled',
                'event_id': event_id
            })

        try:
            # Call the specific handler
            event_data = event.get('data', {}).get('object', {})
            result = handler(event_data, event_id)

            if result.success:
                self.log_info(
                    f"Successfully handled {event_type}",
                    event_id=event_id
                )
            else:
                self.log_error(
                    f"Handler failed for {event_type}: {result.error}",
                    event_id=event_id,
                    error_code=result.error_code
                )

            return result

        except Exception as e:
            self.log_error(
                f"Exception handling {event_type}",
                exception=e,
                event_id=event_id
            )
            return ServiceResult.fail(
                f"Failed to process event: {str(e)}",
                error_code="HANDLER_EXCEPTION"
            )

    @transaction.atomic
    def handle_payment_intent_succeeded(
        self,
        payment_intent: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle successful payment.
        Updates related orders to 'paid' status.

        Args:
            payment_intent: Stripe PaymentIntent object
            event_id: Webhook event ID

        Returns:
            ServiceResult with updated order count
        """
        intent_id = payment_intent.get('id')
        metadata = payment_intent.get('metadata', {})
        amount = payment_intent.get('amount', 0)

        self.log_info(
            f"Payment intent succeeded: {intent_id}",
            amount=amount,
            metadata=metadata
        )

        # Extract order IDs from metadata
        order_ids_str = metadata.get('order_ids', '')
        order_id_single = metadata.get('order_id')  # Legacy single order

        order_ids = []
        if order_ids_str:
            try:
                # Parse comma-separated order IDs
                order_ids = [int(id.strip())
                             for id in order_ids_str.split(',') if id.strip()]
            except ValueError:
                self.log_error(
                    f"Invalid order_ids in metadata: {order_ids_str}")
        elif order_id_single:
            try:
                order_ids = [int(order_id_single)]
            except ValueError:
                self.log_error(
                    f"Invalid order_id in metadata: {order_id_single}")

        if not order_ids:
            # Check if it's a group buying payment
            group_id = metadata.get('group_id')
            buyer_id = metadata.get('buyer_id')

            if group_id and buyer_id:
                return self._handle_group_payment_succeeded(
                    payment_intent,
                    int(group_id),
                    int(buyer_id)
                )

            self.log_warning(
                "Payment intent has no order_ids or group_id in metadata",
                intent_id=intent_id
            )
            return ServiceResult.fail(
                "No orders found in payment metadata",
                error_code="NO_ORDERS"
            )

        # Update orders
        orders = Order.objects.filter(id__in=order_ids).select_for_update()
        updated_count = 0
        skipped_count = 0

        now = timezone.now()

        for order in orders:
            # Check if already paid
            if order.status == 'paid':
                skipped_count += 1
                continue

            # Verify payment intent matches
            if order.stripe_payment_intent_id and order.stripe_payment_intent_id != intent_id:
                self.log_warning(
                    f"Payment intent mismatch for order {order.id}",
                    expected=order.stripe_payment_intent_id,
                    received=intent_id
                )
                continue

            # Update order
            order.status = 'paid'
            order.paid_at = now
            if not order.stripe_payment_intent_id:
                order.stripe_payment_intent_id = intent_id
            order.save(update_fields=[
                       'status', 'paid_at', 'stripe_payment_intent_id'])

            updated_count += 1

            self.log_info(
                f"Marked order {order.reference_number} as paid",
                order_id=order.id,
                reference=order.reference_number
            )

        return ServiceResult.ok({
            'orders_updated': updated_count,
            'orders_skipped': skipped_count,
            'order_ids': order_ids
        })

    def handle_payment_intent_failed(
        self,
        payment_intent: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle failed payment.
        Logs failure details for investigation.

        Args:
            payment_intent: Stripe PaymentIntent object
            event_id: Webhook event ID

        Returns:
            ServiceResult with failure details
        """
        intent_id = payment_intent.get('id')
        amount = payment_intent.get('amount', 0)
        metadata = payment_intent.get('metadata', {})
        last_error = payment_intent.get('last_payment_error', {})

        error_message = last_error.get('message', 'Unknown error')
        error_code = last_error.get('code', 'unknown')

        self.log_error(
            f"Payment intent failed: {intent_id}",
            amount=amount,
            error_message=error_message,
            error_code=error_code,
            metadata=metadata
        )

        # Could send notification to buyer here
        # Could update order with failure reason

        return ServiceResult.ok({
            'payment_failed': True,
            'intent_id': intent_id,
            'error': error_message,
            'error_code': error_code
        })

    def handle_payment_intent_canceled(
        self,
        payment_intent: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle canceled payment intent.
        This happens when group buying fails or buyer cancels.

        Args:
            payment_intent: Stripe PaymentIntent object
            event_id: Webhook event ID

        Returns:
            ServiceResult with cancellation details
        """
        intent_id = payment_intent.get('id')
        metadata = payment_intent.get('metadata', {})

        self.log_info(
            f"Payment intent canceled: {intent_id}",
            metadata=metadata
        )

        # Check if it's a group buying cancellation
        group_id = metadata.get('group_id')
        if group_id:
            try:
                # Update group commitment status
                commitment = GroupCommitment.objects.get(
                    group_id=group_id,
                    stripe_payment_intent_id=intent_id
                )
                commitment.status = 'cancelled'
                commitment.save(update_fields=['status'])

                self.log_info(
                    f"Marked group commitment as cancelled",
                    commitment_id=commitment.id
                )
            except GroupCommitment.DoesNotExist:
                pass

        return ServiceResult.ok({
            'payment_canceled': True,
            'intent_id': intent_id
        })

    @transaction.atomic
    def handle_account_updated(
        self,
        account: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle Stripe Connect account updates.
        Updates vendor onboarding status when account is verified.

        Args:
            account: Stripe Account object
            event_id: Webhook event ID

        Returns:
            ServiceResult with update status
        """
        account_id = account.get('id')
        charges_enabled = account.get('charges_enabled', False)
        payouts_enabled = account.get('payouts_enabled', False)

        self.log_info(
            f"Account updated: {account_id}",
            charges_enabled=charges_enabled,
            payouts_enabled=payouts_enabled
        )

        try:
            vendor = Vendor.objects.select_for_update().get(
                stripe_account_id=account_id
            )

            # Update vendor status
            old_status = vendor.stripe_onboarding_complete
            vendor.stripe_onboarding_complete = charges_enabled
            vendor.save(update_fields=['stripe_onboarding_complete'])

            status_changed = old_status != charges_enabled

            if status_changed:
                self.log_info(
                    f"Vendor {vendor.id} onboarding status changed",
                    vendor_id=vendor.id,
                    old_status=old_status,
                    new_status=charges_enabled
                )

                # Could send notification to vendor here

            return ServiceResult.ok({
                'vendor_id': vendor.id,
                'status_changed': status_changed,
                'charges_enabled': charges_enabled,
                'payouts_enabled': payouts_enabled
            })

        except Vendor.DoesNotExist:
            self.log_warning(
                f"Vendor not found for account: {account_id}"
            )
            return ServiceResult.fail(
                "Vendor not found",
                error_code="VENDOR_NOT_FOUND"
            )

    def handle_payout_paid(
        self,
        payout: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle successful vendor payout.
        Logs payout details for reconciliation.

        Args:
            payout: Stripe Payout object
            event_id: Webhook event ID

        Returns:
            ServiceResult with payout details
        """
        payout_id = payout.get('id')
        amount = payout.get('amount', 0)
        arrival_date = payout.get('arrival_date')
        destination = payout.get('destination')

        # Convert amount from pence to pounds
        amount_gbp = Decimal(amount) / 100

        self.log_info(
            f"Payout completed: {payout_id}",
            amount_gbp=float(amount_gbp),
            arrival_date=arrival_date,
            destination=destination
        )

        # Could update vendor balance tracking here
        # Could send notification to vendor here

        return ServiceResult.ok({
            'payout_id': payout_id,
            'amount': amount,
            'amount_gbp': float(amount_gbp),
            'arrival_date': datetime.fromtimestamp(arrival_date) if arrival_date else None
        })

    @transaction.atomic
    def handle_charge_refunded(
        self,
        refund: Dict[str, Any],
        event_id: str
    ) -> ServiceResult:
        """
        Handle refund event.
        Updates related order status if full refund.

        Args:
            refund: Stripe Refund object
            event_id: Webhook event ID

        Returns:
            ServiceResult with refund details
        """
        refund_id = refund.get('id')
        amount = refund.get('amount', 0)
        payment_intent = refund.get('payment_intent')
        status = refund.get('status')
        reason = refund.get('reason', 'requested_by_customer')

        amount_gbp = Decimal(amount) / 100

        self.log_info(
            f"Refund processed: {refund_id}",
            amount_gbp=float(amount_gbp),
            payment_intent=payment_intent,
            reason=reason
        )

        if payment_intent:
            # Find orders with this payment intent
            orders = Order.objects.filter(
                stripe_payment_intent_id=payment_intent
            ).select_for_update()

            updated_count = 0
            for order in orders:
                # Check if full refund
                order_amount_pence = int(order.total * 100)

                if amount >= order_amount_pence and order.status != 'refunded':
                    order.status = 'refunded'
                    order.save(update_fields=['status'])
                    updated_count += 1

                    self.log_info(
                        f"Marked order {order.reference_number} as refunded",
                        order_id=order.id
                    )

            return ServiceResult.ok({
                'refund_id': refund_id,
                'amount': amount,
                'orders_updated': updated_count
            })

        return ServiceResult.ok({
            'refund_id': refund_id,
            'amount': amount,
            'orders_updated': 0
        })

    def _handle_group_payment_succeeded(
        self,
        payment_intent: Dict[str, Any],
        group_id: int,
        buyer_id: int
    ) -> ServiceResult:
        """
        Handle successful payment for group buying commitment.

        Args:
            payment_intent: Stripe PaymentIntent object
            group_id: BuyingGroup ID
            buyer_id: Buyer user ID

        Returns:
            ServiceResult with update status
        """
        intent_id = payment_intent.get('id')

        try:
            commitment = GroupCommitment.objects.select_for_update().get(
                group_id=group_id,
                buyer_id=buyer_id
            )

            if commitment.status == 'confirmed':
                # Already processed
                return ServiceResult.ok({
                    'message': 'Commitment already confirmed',
                    'commitment_id': commitment.id
                })

            # Update commitment
            commitment.status = 'confirmed'
            commitment.stripe_payment_intent_id = intent_id
            commitment.save(
                update_fields=['status', 'stripe_payment_intent_id'])

            self.log_info(
                f"Confirmed group commitment payment",
                commitment_id=commitment.id,
                group_id=group_id
            )

            return ServiceResult.ok({
                'commitment_confirmed': True,
                'commitment_id': commitment.id
            })

        except GroupCommitment.DoesNotExist:
            self.log_warning(
                f"Group commitment not found",
                group_id=group_id,
                buyer_id=buyer_id
            )
            return ServiceResult.fail(
                "Group commitment not found",
                error_code="COMMITMENT_NOT_FOUND"
            )
