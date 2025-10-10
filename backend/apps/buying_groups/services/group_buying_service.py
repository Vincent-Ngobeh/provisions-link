"""
Group buying service for managing location-based group purchases.
This service handles the core business logic for group buying features.
WebSocket broadcasting for real-time updates.
"""
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from apps.core.services.base import (
    BaseService, ServiceException, ValidationError,
    BusinessRuleViolation, ServiceResult
)
from apps.buying_groups.models import BuyingGroup, GroupCommitment, GroupUpdate
from apps.products.models import Product
from apps.core.models import User
from apps.core.utils.websocket_utils import broadcaster  # ADD THIS IMPORT


class GroupBuyingService(BaseService):
    """
    Service for managing group buying operations.
    Handles group creation, commitment processing, and threshold calculations.
    Now includes real-time WebSocket broadcasting.
    """

    # Business rule constants
    MIN_GROUP_DURATION_HOURS = 24
    MAX_GROUP_DURATION_DAYS = 30
    MIN_DISCOUNT_PERCENT = Decimal('5.00')
    MAX_DISCOUNT_PERCENT = Decimal('50.00')
    DEFAULT_RADIUS_KM = 5
    DEFAULT_MIN_QUANTITY_RATIO = Decimal(
        '0.60')  # Min quantity is 60% of target

    def create_group_for_area(
        self,
        product_id: int,
        postcode: str,
        target_quantity: Optional[int] = None,
        discount_percent: Optional[Decimal] = None,
        duration_days: Optional[int] = 7,
        radius_km: Optional[int] = None
    ) -> ServiceResult:
        """
        Create a new buying group centered on a postcode area.

        Args:
            product_id: ID of the product for group buying
            postcode: UK postcode for the center of the group
            target_quantity: Target quantity to achieve discount (auto-calculated if None)
            discount_percent: Discount percentage when target reached (auto-calculated if None)
            duration_days: How long the group runs for (default 7 days)
            radius_km: Radius for the group area (default 5km)

        Returns:
            ServiceResult containing the created BuyingGroup or error
        """
        try:
            # Validate inputs
            if duration_days > self.MAX_GROUP_DURATION_DAYS:
                return ServiceResult.fail(
                    f"Group duration cannot exceed {self.MAX_GROUP_DURATION_DAYS} days",
                    error_code="DURATION_TOO_LONG"
                )

            if duration_days < 1:
                return ServiceResult.fail(
                    "Group duration must be at least 1 day",
                    error_code="DURATION_TOO_SHORT"
                )

            # Get product
            try:
                product = Product.objects.select_related(
                    'vendor').get(id=product_id)
            except Product.DoesNotExist:
                return ServiceResult.fail(
                    f"Product with ID {product_id} not found",
                    error_code="PRODUCT_NOT_FOUND"
                )

            # Check product availability
            if not product.is_active:
                return ServiceResult.fail(
                    "Product is not active",
                    error_code="PRODUCT_INACTIVE"
                )

            if product.stock_quantity < 10:  # Minimum stock for group buying
                return ServiceResult.fail(
                    "Insufficient stock for group buying",
                    error_code="INSUFFICIENT_STOCK"
                )

            # Geocode postcode
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()
            location_result = geo_service.geocode_postcode(postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Could not geocode postcode: {location_result.error}",
                    error_code="GEOCODING_FAILED"
                )

            center_point = location_result.data['point']
            area_name = location_result.data.get(
                'area_name', f"{postcode} area")

            # Auto-calculate target quantity and discount if not provided
            if target_quantity is None:
                target_quantity = self._calculate_target_quantity(product)

            if discount_percent is None:
                discount_percent = self._calculate_discount_percent(
                    product, target_quantity)

            # Validate discount percent
            if discount_percent < self.MIN_DISCOUNT_PERCENT:
                discount_percent = self.MIN_DISCOUNT_PERCENT
            elif discount_percent > self.MAX_DISCOUNT_PERCENT:
                discount_percent = self.MAX_DISCOUNT_PERCENT

            # Calculate minimum quantity (60% of target)
            min_quantity = int(target_quantity *
                               self.DEFAULT_MIN_QUANTITY_RATIO)

            # Set expiry date
            expires_at = timezone.now() + timedelta(days=duration_days)

            # Create the group
            with transaction.atomic():
                group = BuyingGroup.objects.create(
                    product=product,
                    center_point=center_point,
                    radius_km=radius_km or self.DEFAULT_RADIUS_KM,
                    area_name=area_name,
                    target_quantity=target_quantity,
                    min_quantity=min_quantity,
                    discount_percent=discount_percent,
                    expires_at=expires_at,
                    status='open'
                )

                # Create initial group update for tracking
                GroupUpdate.objects.create(
                    group=group,
                    event_type='commitment',
                    event_data={
                        'message': f"Group buying started for {product.name}",
                        'area': area_name,
                        'target': target_quantity,
                        'discount': str(discount_percent)
                    }
                )

                self.log_info(
                    f"Created buying group {group.id} for product {product.name}",
                    group_id=group.id,
                    product_id=product.id
                )

                return ServiceResult.ok(group)

        except Exception as e:
            self.log_error(f"Error creating buying group", exception=e)
            return ServiceResult.fail(
                "Failed to create buying group",
                error_code="CREATE_FAILED"
            )

    def _calculate_target_quantity(self, product: Product) -> int:
        """
        Calculate smart target quantity based on product price.

        Args:
            product: The product for group buying

        Returns:
            Calculated target quantity
        """
        # Higher priced items need fewer buyers
        if product.price > 100:
            return 10
        elif product.price > 50:
            return 20
        elif product.price > 20:
            return 30
        else:
            return 50

    def _calculate_discount_percent(self, product: Product, target_quantity: int) -> Decimal:
        """
        Calculate smart discount percentage based on product and quantity.

        Args:
            product: The product for group buying
            target_quantity: The target quantity for the group

        Returns:
            Calculated discount percentage
        """
        # Higher quantities get better discounts
        if target_quantity >= 50:
            base_discount = Decimal('15.00')
        elif target_quantity >= 30:
            base_discount = Decimal('12.00')
        elif target_quantity >= 20:
            base_discount = Decimal('10.00')
        else:
            base_discount = Decimal('8.00')

        # Expensive items get slightly lower discounts (vendor margins)
        if product.price > 100:
            return base_discount - Decimal('2.00')

        return base_discount

    @transaction.atomic
    def commit_to_group(
        self,
        group_id: int,
        buyer: User,
        quantity: int,
        buyer_postcode: str
    ) -> ServiceResult:
        """
        Commit a buyer to a group purchase with real-time updates.

        Args:
            group_id: ID of the buying group
            buyer: User making the commitment
            quantity: Quantity to commit to purchase
            buyer_postcode: Buyer's postcode for location verification

        Returns:
            ServiceResult containing the GroupCommitment or error
        """
        try:
            # Get group with lock to prevent race conditions
            try:
                group = BuyingGroup.objects.select_for_update().get(id=group_id)
            except BuyingGroup.DoesNotExist:
                return ServiceResult.fail(
                    f"Buying group {group_id} not found",
                    error_code="GROUP_NOT_FOUND"
                )

            # Validate group status
            if group.status != 'open':
                return ServiceResult.fail(
                    "This buying group is no longer accepting commitments",
                    error_code="GROUP_CLOSED"
                )

            # Check if group has expired
            if group.is_expired:
                group.update_status()
                return ServiceResult.fail(
                    "This buying group has expired",
                    error_code="GROUP_EXPIRED"
                )

            # Check if buyer already has a commitment
            existing = GroupCommitment.objects.filter(
                group=group,
                buyer=buyer,
                status='pending'
            ).first()

            if existing:
                return ServiceResult.fail(
                    "You already have an active commitment to this group",
                    error_code="DUPLICATE_COMMITMENT"
                )

            # Validate quantity
            if quantity <= 0:
                return ServiceResult.fail(
                    "Quantity must be positive",
                    error_code="INVALID_QUANTITY"
                )

            # Check if quantity would exceed product stock
            total_after = group.current_quantity + quantity
            if total_after > group.product.stock_quantity:
                return ServiceResult.fail(
                    "Quantity exceeds available stock",
                    error_code="EXCEEDS_STOCK"
                )

            # Geocode buyer location
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()
            location_result = geo_service.geocode_postcode(buyer_postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Could not verify location: {location_result.error}",
                    error_code="LOCATION_VERIFICATION_FAILED"
                )

            buyer_location = location_result.data['point']

            # Verify buyer is within group radius
            if not group.can_join(buyer_location):
                return ServiceResult.fail(
                    f"Your location is outside the {group.radius_km}km group area",
                    error_code="OUTSIDE_RADIUS"
                )

            # Calculate payment amount
            amount = self.calculate_commitment_amount(group, quantity)

            # Create Stripe payment intent (pre-authorization)
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()

            payment_result = stripe_service.create_payment_intent_for_group(
                amount=amount,
                group_id=group_id,
                buyer_id=buyer.id
            )

            if not payment_result.success:
                return ServiceResult.fail(
                    f"Payment pre-authorization failed: {payment_result.error}",
                    error_code="PAYMENT_FAILED"
                )

            # Create commitment
            commitment = GroupCommitment.objects.create(
                group=group,
                buyer=buyer,
                quantity=quantity,
                buyer_location=buyer_location,
                buyer_postcode=buyer_postcode,
                stripe_payment_intent_id=payment_result.data['intent_id'],
                status='pending'
            )

            # Update group quantity
            group.current_quantity = F('current_quantity') + quantity
            group.save(update_fields=['current_quantity'])

            # Refresh from DB to get updated value
            group.refresh_from_db()

            # Get updated counts for broadcasting
            participants_count = group.commitments.filter(
                status='pending').count()
            progress_percent = float(group.progress_percent)

            # Calculate time remaining
            time_remaining = group.time_remaining
            time_remaining_seconds = int(
                time_remaining.total_seconds()) if time_remaining else 0

            # WEBSOCKET: Broadcast progress update
            broadcaster.broadcast_progress(
                group_id=group.id,
                current_quantity=group.current_quantity,
                target_quantity=group.target_quantity,
                participants_count=participants_count,
                progress_percent=progress_percent,
                time_remaining_seconds=time_remaining_seconds
            )

            # WEBSOCKET: Broadcast new commitment
            buyer_name = buyer.get_full_name() or buyer.username or 'A buyer'
            broadcaster.broadcast_new_commitment(
                group_id=group.id,
                buyer_name=buyer_name,
                quantity=quantity,
                new_total=group.current_quantity,
                participants_count=participants_count
            )

            # WEBSOCKET: Check if threshold reached (80%)
            old_progress = progress_percent - \
                (quantity / group.target_quantity * 100)
            if progress_percent >= 80 and old_progress < 80:
                broadcaster.broadcast_threshold_reached(
                    group_id=group.id,
                    threshold_percent=80,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity
                )

            # Check if target reached
            if group.current_quantity >= group.target_quantity:
                self._handle_target_reached(group)

            # Create update event for database tracking
            GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={
                    'buyer_id': buyer.id,
                    'quantity': quantity,
                    'current_total': group.current_quantity,
                    'progress_percent': progress_percent
                }
            )

            self.log_info(
                f"Commitment created for buyer {buyer.id} in group {group.id}",
                commitment_id=commitment.id,
                quantity=quantity
            )

            # FIXED: Return just the commitment object, not a dict
            return ServiceResult.ok(commitment)

        except Exception as e:
            self.log_error(f"Error creating commitment", exception=e)
            return ServiceResult.fail(
                "Failed to create commitment",
                error_code="COMMITMENT_FAILED"
            )

    def calculate_commitment_amount(self, group: BuyingGroup, quantity: int) -> Decimal:
        """
        Calculate the total amount for a commitment including discount.

        Args:
            group: The buying group
            quantity: Quantity being committed

        Returns:
            Total amount with discount applied
        """
        unit_price = group.product.price
        discount_multiplier = 1 - (group.discount_percent / 100)
        subtotal = unit_price * quantity * discount_multiplier
        vat_amount = subtotal * group.product.vat_rate
        return subtotal + vat_amount

    def _handle_target_reached(self, group: BuyingGroup) -> None:
        """
        Handle actions when a group reaches its target with WebSocket notification.

        Args:
            group: The buying group that reached target
        """
        old_status = group.status

        # Update status
        group.status = 'active'
        group.save(update_fields=['status'])

        # WEBSOCKET: Broadcast status change
        broadcaster.broadcast_status_change(
            group_id=group.id,
            old_status=old_status,
            new_status='active',
            reason='Target quantity reached!'
        )

        # Create notification event for database
        GroupUpdate.objects.create(
            group=group,
            event_type='threshold',
            event_data={
                'message': 'Target quantity reached! Group discount unlocked.',
                'target': group.target_quantity,
                'current': group.current_quantity,
                'discount': str(group.discount_percent)
            }
        )

        # TODO: Send notifications to all participants
        # This would integrate with notification service

        self.log_info(
            f"Group {group.id} reached target quantity",
            group_id=group.id,
            target=group.target_quantity
        )

    def cancel_commitment(self, commitment_id: int, buyer: User) -> ServiceResult:
        """
        Cancel a buyer's commitment to a group with WebSocket notifications.

        Args:
            commitment_id: ID of the commitment to cancel
            buyer: User requesting cancellation

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            commitment = GroupCommitment.objects.select_related('group').get(
                id=commitment_id,
                buyer=buyer
            )

            if commitment.status != 'pending':
                return ServiceResult.fail(
                    "Cannot cancel a processed commitment",
                    error_code="CANNOT_CANCEL"
                )

            if commitment.group.status != 'open':
                return ServiceResult.fail(
                    "Cannot cancel after group has been processed",
                    error_code="GROUP_PROCESSED"
                )

            with transaction.atomic():
                # Cancel Stripe payment intent
                from apps.integrations.services.stripe_service import StripeConnectService
                stripe_service = StripeConnectService()

                cancel_result = stripe_service.cancel_payment_intent(
                    commitment.stripe_payment_intent_id
                )

                if not cancel_result.success:
                    self.log_warning(
                        f"Failed to cancel Stripe intent: {cancel_result.error}"
                    )

                # Update commitment status
                commitment.status = 'cancelled'
                commitment.save(update_fields=['status'])

                # Update group quantity
                group = commitment.group
                group.current_quantity = F(
                    'current_quantity') - commitment.quantity
                group.save(update_fields=['current_quantity'])
                group.refresh_from_db()

                # Get updated counts for broadcasting
                participants_count = group.commitments.filter(
                    status='pending').count()
                progress_percent = float(group.progress_percent)
                time_remaining = group.time_remaining
                time_remaining_seconds = int(
                    time_remaining.total_seconds()) if time_remaining else 0

                # WEBSOCKET: Broadcast the cancellation
                broadcaster.broadcast_commitment_cancelled(
                    group_id=group.id,
                    quantity=commitment.quantity,
                    new_total=group.current_quantity,
                    participants_count=participants_count
                )

                # WEBSOCKET: Broadcast updated progress
                broadcaster.broadcast_progress(
                    group_id=group.id,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity,
                    participants_count=participants_count,
                    progress_percent=progress_percent,
                    time_remaining_seconds=time_remaining_seconds
                )

                # Create update event for database
                GroupUpdate.objects.create(
                    group=group,
                    event_type='cancelled',
                    event_data={
                        'buyer_id': buyer.id,
                        'quantity': commitment.quantity,
                        'current_total': group.current_quantity
                    }
                )

                self.log_info(
                    f"Commitment {commitment_id} cancelled",
                    commitment_id=commitment_id,
                    buyer_id=buyer.id
                )

                return ServiceResult.ok({
                    "message": "Commitment cancelled successfully",
                    "refunded_quantity": commitment.quantity
                })

        except GroupCommitment.DoesNotExist:
            return ServiceResult.fail(
                "Commitment not found",
                error_code="NOT_FOUND"
            )
        except Exception as e:
            self.log_error(f"Error cancelling commitment", exception=e)
            return ServiceResult.fail(
                "Failed to cancel commitment",
                error_code="CANCEL_FAILED"
            )

    def update_group_status(
        self,
        group_id: int,
        new_status: str,
        reason: Optional[str] = None
    ) -> ServiceResult:
        """
        Update group status with WebSocket notification.

        Args:
            group_id: BuyingGroup ID
            new_status: New status to set
            reason: Optional reason for the change

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            group = BuyingGroup.objects.get(id=group_id)

            old_status = group.status

            # Validate status transition
            valid_transitions = {
                'open': ['active', 'failed', 'cancelled'],
                'active': ['completed', 'cancelled'],
                'failed': [],  # Terminal state
                'completed': [],  # Terminal state
                'cancelled': []  # Terminal state
            }

            if new_status not in valid_transitions.get(old_status, []):
                return ServiceResult.fail(
                    f"Invalid status transition from {old_status} to {new_status}",
                    error_code="INVALID_TRANSITION"
                )

            group.status = new_status
            group.save(update_fields=['status'])

            # WEBSOCKET: Broadcast status change
            broadcaster.broadcast_status_change(
                group_id=group.id,
                old_status=old_status,
                new_status=new_status,
                reason=reason
            )

            self.log_info(
                f"Group status updated",
                group_id=group_id,
                old_status=old_status,
                new_status=new_status
            )

            return ServiceResult.ok({
                'group_id': group_id,
                'old_status': old_status,
                'new_status': new_status
            })

        except BuyingGroup.DoesNotExist:
            return ServiceResult.fail(
                "Group not found",
                error_code="GROUP_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error updating group status",
                exception=e,
                group_id=group_id
            )
            return ServiceResult.fail(
                "Failed to update group status",
                error_code="UPDATE_FAILED"
            )

    def process_expired_groups(self) -> Dict[str, Any]:
        """
        Process all expired groups and update their status.
        This would be called by a Celery periodic task.

        Returns:
            Dictionary with processing statistics
        """
        expired_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__lte=timezone.now()
        )

        stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0
        }

        for group in expired_groups:
            try:
                with transaction.atomic():
                    old_status = group.status

                    if group.current_quantity >= group.min_quantity:
                        # Group succeeded
                        group.status = 'active'
                        self._process_successful_group(group)
                        stats['successful'] += 1

                        # WEBSOCKET: Broadcast success
                        broadcaster.broadcast_status_change(
                            group_id=group.id,
                            old_status=old_status,
                            new_status='active',
                            reason='Minimum quantity reached at expiry'
                        )
                    else:
                        # Group failed
                        group.status = 'failed'
                        self._process_failed_group(group)
                        stats['failed'] += 1

                        # WEBSOCKET: Broadcast failure
                        broadcaster.broadcast_status_change(
                            group_id=group.id,
                            old_status=old_status,
                            new_status='failed',
                            reason='Minimum quantity not reached'
                        )

                    group.save(update_fields=['status'])

                    # Create update event
                    GroupUpdate.objects.create(
                        group=group,
                        event_type='expired',
                        event_data={
                            'final_status': group.status,
                            'final_quantity': group.current_quantity,
                            'target': group.target_quantity,
                            'min_required': group.min_quantity
                        }
                    )

                stats['total_processed'] += 1

            except Exception as e:
                self.log_error(
                    f"Error processing expired group {group.id}",
                    exception=e
                )

        self.log_info(f"Processed expired groups", stats=stats)
        return stats

    def _process_successful_group(self, group: BuyingGroup) -> None:
        """
        Process a successful group (create orders, capture payments).

        Args:
            group: The successful buying group
        """
        # This will be implemented with OrderService
        # For now, just log
        self.log_info(
            f"Processing successful group {group.id}",
            group_id=group.id,
            quantity=group.current_quantity
        )

        # TODO: Implement order creation
        # from apps.orders.services.order_service import OrderService
        # order_service = OrderService()
        # for commitment in group.commitments.filter(status='pending'):
        #     order_service.create_from_commitment(commitment)

    def _process_failed_group(self, group: BuyingGroup) -> None:
        """
        Process a failed group (release payment holds, notify users).

        Args:
            group: The failed buying group
        """
        # Cancel all payment intents
        from apps.integrations.services.stripe_service import StripeConnectService
        stripe_service = StripeConnectService()

        commitments = group.commitments.filter(status='pending')

        for commitment in commitments:
            try:
                stripe_service.cancel_payment_intent(
                    commitment.stripe_payment_intent_id
                )
                commitment.status = 'cancelled'
                commitment.save(update_fields=['status'])
            except Exception as e:
                self.log_error(
                    f"Error cancelling payment for commitment {commitment.id}",
                    exception=e
                )

        self.log_info(
            f"Processed failed group {group.id}",
            group_id=group.id,
            cancelled_commitments=commitments.count()
        )
