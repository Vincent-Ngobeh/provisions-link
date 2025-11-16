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
from apps.core.utils.websocket_utils import broadcaster
from apps.core.models import Address


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

        # Factor in product price (more expensive = higher discount)
        if product.price > 100:
            base_discount += Decimal('5.00')
        elif product.price > 50:
            base_discount += Decimal('3.00')

        return base_discount

    def find_nearby_groups(
        self,
        product_id: int,
        postcode: str,
        radius_km: Optional[int] = None
    ) -> ServiceResult:
        """
        Find active buying groups near a postcode for a product.

        Args:
            product_id: ID of the product to find groups for
            postcode: User's postcode
            radius_km: Search radius (defaults to DEFAULT_RADIUS_KM)

        Returns:
            ServiceResult containing list of nearby groups or error
        """
        try:
            # Geocode postcode
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()
            location_result = geo_service.geocode_postcode(postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Could not geocode postcode: {location_result.error}",
                    error_code="GEOCODING_FAILED"
                )

            user_point = location_result.data['point']
            search_radius = radius_km or self.DEFAULT_RADIUS_KM

            # Find groups within radius
            nearby_groups = BuyingGroup.objects.filter(
                product_id=product_id,
                status='open',
                expires_at__gt=timezone.now(),
                center_point__distance_lte=(
                    user_point, D(km=search_radius))
            ).select_related('product', 'product__vendor')

            # Add distance annotation
            nearby_groups = nearby_groups.annotate(
                distance_km=F('center_point').distance(user_point) / 1000
            ).order_by('distance_km')

            self.log_info(
                f"Found {nearby_groups.count()} groups near {postcode}",
                product_id=product_id,
                postcode=postcode
            )

            return ServiceResult.ok({
                'groups': list(nearby_groups),
                'count': nearby_groups.count(),
                'search_radius_km': search_radius
            })

        except Exception as e:
            self.log_error(f"Error finding nearby groups", exception=e)
            return ServiceResult.fail(
                "Failed to find nearby groups",
                error_code="SEARCH_FAILED"
            )

    def create_payment_intent_for_commitment(
        self,
        group_id: int,
        buyer: User,
        quantity: int,
        buyer_postcode: str,
        delivery_address_id: int
    ) -> ServiceResult:
        """
        Create a Stripe payment intent for a group commitment WITHOUT creating the commitment yet.
        This is step 1 of the two-step payment flow.

        Args:
            group_id: ID of the group to join
            buyer: User who wants to commit
            quantity: Quantity they want to buy
            buyer_postcode: Buyer's postcode (for distance calculation)
            delivery_address_id: ID of delivery address

        Returns:
            ServiceResult containing payment intent details (client_secret, intent_id)
        """
        try:
            # Validate delivery address
            try:
                delivery_address = Address.objects.get(
                    id=delivery_address_id, user=buyer)
            except Address.DoesNotExist:
                return ServiceResult.fail(
                    "Invalid delivery address",
                    error_code="INVALID_ADDRESS"
                )

            # Get group to calculate payment amount
            try:
                group = BuyingGroup.objects.select_related(
                    'product__vendor').get(id=group_id)
            except BuyingGroup.DoesNotExist:
                return ServiceResult.fail(
                    "Group not found",
                    error_code="GROUP_NOT_FOUND"
                )

            # Calculate prices with group discount
            product = group.product
            vendor = product.vendor

            unit_price = product.price
            discount_multiplier = 1 - (group.discount_percent / 100)
            discounted_price = unit_price * discount_multiplier
            subtotal = discounted_price * quantity
            vat_amount = subtotal * product.vat_rate

            # Calculate delivery fee using selected address
            from apps.orders.services.order_service import OrderService
            order_service = OrderService()
            delivery_fee = order_service._calculate_delivery_fee(
                subtotal,
                vendor,
                delivery_address
            )

            # Calculate total including delivery fee
            total = subtotal + vat_amount + delivery_fee

            # Create Stripe payment intent for pre-authorization
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()

            payment_result = stripe_service.create_payment_intent_for_group(
                amount=total,
                group_id=group_id,
                buyer_id=buyer.id
            )

            if not payment_result.success:
                return ServiceResult.fail(
                    f"Failed to create payment intent: {payment_result.error}",
                    error_code="PAYMENT_INTENT_FAILED"
                )

            self.log_info(
                f"Created payment intent for group {group_id}",
                group_id=group_id,
                buyer_id=buyer.id,
                amount=float(total),
                intent_id=payment_result.data['intent_id']
            )

            return ServiceResult.ok({
                'client_secret': payment_result.data['client_secret'],
                'intent_id': payment_result.data['intent_id'],
                'amount': total,
                'group': group
            })

        except Exception as e:
            self.log_error(
                f"Error creating payment intent",
                exception=e,
                group_id=group_id,
                buyer_id=buyer.id
            )
            return ServiceResult.fail(
                "Failed to create payment intent",
                error_code="PAYMENT_INTENT_CREATION_FAILED"
            )

    def commit_to_group(
        self,
        group_id: int,
        buyer: User,
        quantity: int,
        buyer_postcode: str,
        delivery_address_id: int,
        delivery_notes: Optional[str] = None,
        payment_intent_id: Optional[str] = None
    ) -> ServiceResult:
        """
        Wrapper method for committing to a group buying deal.
        Handles geocoding and delegates to join_group.

        Args:
            group_id: ID of the group to join
            buyer: User making the commitment
            quantity: Quantity they want to buy
            buyer_postcode: Buyer's postcode (will be geocoded)
            delivery_address_id: ID of delivery address
            delivery_notes: Optional delivery notes
            payment_intent_id: Optional pre-confirmed payment intent ID

        Returns:
            ServiceResult containing commitment details or error
        """
        try:
            try:
                delivery_address = Address.objects.get(
                    id=delivery_address_id, user=buyer)
            except Address.DoesNotExist:
                return ServiceResult.fail(
                    "Invalid delivery address",
                    error_code="INVALID_ADDRESS"
                )

            # Geocode the buyer's postcode
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()
            location_result = geo_service.geocode_postcode(buyer_postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Could not geocode postcode: {location_result.error}",
                    error_code="GEOCODING_FAILED"
                )

            buyer_location = location_result.data['point']

            # Get group to calculate payment amount
            try:
                group = BuyingGroup.objects.select_related(
                    'product__vendor').get(id=group_id)
            except BuyingGroup.DoesNotExist:
                return ServiceResult.fail(
                    "Group not found",
                    error_code="GROUP_NOT_FOUND"
                )

            # Calculate prices with group discount
            product = group.product
            vendor = product.vendor

            unit_price = product.price
            discount_multiplier = 1 - (group.discount_percent / 100)
            discounted_price = unit_price * discount_multiplier
            subtotal = discounted_price * quantity
            vat_amount = subtotal * product.vat_rate

            # IMPORTANT: Calculate delivery fee DURING join using selected address
            from apps.orders.services.order_service import OrderService
            order_service = OrderService()
            delivery_fee = order_service._calculate_delivery_fee(
                subtotal,
                vendor,
                delivery_address
            )

            # Calculate total including delivery fee
            total = subtotal + vat_amount + delivery_fee

            # Handle payment intent
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()

            # Two-step payment flow support
            if payment_intent_id:
                # Payment intent already created and confirmed by frontend
                # Verify it exists and is in correct state
                self.log_info(
                    f"Using pre-confirmed payment intent {payment_intent_id}",
                    group_id=group_id,
                    buyer_id=buyer.id,
                    payment_intent_id=payment_intent_id
                )
                # Store the already-confirmed payment_intent_id for commitment
                final_payment_intent_id = payment_intent_id
                payment_result = None  # No new payment intent created
            else:
                # Legacy flow: create payment intent now (for backward compatibility)
                # This creates an unconfirmed intent - frontend should confirm it
                payment_result = stripe_service.create_payment_intent_for_group(
                    amount=total,
                    group_id=group_id,
                    buyer_id=buyer.id
                )

                final_payment_intent_id = None
                if payment_result.success:
                    final_payment_intent_id = payment_result.data['intent_id']
                else:
                    # Log warning but don't fail - payment can be collected later
                    self.log_warning(
                        f"Failed to create payment intent: {payment_result.error}",
                        group_id=group_id,
                        buyer_id=buyer.id
                    )

            # Call join_group with all required parameters
            result = self.join_group(
                group_id=group_id,
                buyer=buyer,
                quantity=quantity,
                buyer_location=buyer_location,
                buyer_postcode=buyer_postcode,
                payment_intent_id=final_payment_intent_id,
                delivery_address=delivery_address,
                delivery_notes=delivery_notes
            )

            if result.success:
                # Add payment intent to response
                response_data = result.data.copy()

                # Only include payment_intent if we created one (legacy flow)
                if payment_result:
                    response_data['payment_intent'] = {
                        'client_secret': payment_result.data.get('client_secret') if payment_result.success else None,
                        'intent_id': final_payment_intent_id
                    }

                response_data['progress_percent'] = response_data['group'].progress_percent

                return ServiceResult.ok(response_data)

            return result

        except Exception as e:
            self.log_error(
                f"Error committing to group",
                exception=e,
                group_id=group_id,
                buyer_id=buyer.id
            )
            return ServiceResult.fail(
                "Failed to commit to group",
                error_code="COMMIT_FAILED"
            )

    def cancel_commitment(
        self,
        commitment_id: int,
        buyer: User,
        reason: Optional[str] = None
    ) -> ServiceResult:
        """
        Wrapper method for cancelling a group commitment.
        Validates ownership and delegates to leave_group.

        Args:
            commitment_id: ID of the commitment to cancel
            buyer: User cancelling the commitment
            reason: Optional reason for cancellation

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            # Get the commitment
            try:
                commitment = GroupCommitment.objects.select_related('group').get(
                    id=commitment_id
                )
            except GroupCommitment.DoesNotExist:
                return ServiceResult.fail(
                    "Commitment not found",
                    error_code="COMMITMENT_NOT_FOUND"
                )

            # Verify ownership
            if commitment.buyer != buyer:
                return ServiceResult.fail(
                    "You can only cancel your own commitments",
                    error_code="PERMISSION_DENIED"
                )

            # Check if already cancelled
            if commitment.status == 'cancelled':
                return ServiceResult.fail(
                    "Commitment is already cancelled",
                    error_code="ALREADY_CANCELLED"
                )

            # Check if already confirmed (order created)
            if commitment.status == 'confirmed':
                return ServiceResult.fail(
                    "Cannot cancel confirmed commitment. Contact support.",
                    error_code="CANNOT_CANCEL_CONFIRMED"
                )

            # Delegate to leave_group
            result = self.leave_group(
                group_id=commitment.group.id,
                buyer=buyer,
                reason=reason
            )

            if result.success:
                return ServiceResult.ok({
                    'message': 'Commitment cancelled successfully',
                    'commitment_id': commitment_id,
                    'group_id': commitment.group.id,
                    'quantity_released': commitment.quantity
                })

            return result

        except Exception as e:
            self.log_error(
                f"Error cancelling commitment",
                exception=e,
                commitment_id=commitment_id,
                buyer_id=buyer.id
            )
            return ServiceResult.fail(
                "Failed to cancel commitment",
                error_code="CANCEL_FAILED"
            )

    def join_group(
        self,
        group_id: int,
        buyer: User,
        quantity: int,
        buyer_location: Point,
        buyer_postcode: str,
        payment_intent_id: Optional[str] = None,
        delivery_address: Optional['Address'] = None,
        delivery_notes: Optional[str] = None
    ) -> ServiceResult:
        """
        Allow a buyer to join/commit to a buying group with WebSocket notification.

        Args:
            group_id: ID of the group to join
            buyer: User making the commitment
            quantity: Quantity they want to buy
            buyer_location: Geocoded location of the buyer
            buyer_postcode: Buyer's postcode
            payment_intent_id: Stripe payment intent ID for pre-authorization
            delivery_address: Delivery address for the order
            delivery_notes: Optional delivery notes

        Returns:
            ServiceResult containing the created GroupCommitment or error
        """
        try:
            # Get group with lock to prevent race conditions
            with transaction.atomic():
                group = BuyingGroup.objects.select_for_update().get(
                    id=group_id)

                # Validate group is open and not expired
                if group.status != 'open':
                    return ServiceResult.fail(
                        f"Group is not open (status: {group.status})",
                        error_code="GROUP_NOT_OPEN"
                    )

                if group.expires_at <= timezone.now():
                    return ServiceResult.fail(
                        "Group has expired",
                        error_code="GROUP_EXPIRED"
                    )

                # Check if buyer already committed
                existing = GroupCommitment.objects.filter(
                    group=group,
                    buyer=buyer,
                    status='pending'
                ).first()

                if existing:
                    return ServiceResult.fail(
                        "You have already committed to this group",
                        error_code="ALREADY_COMMITTED"
                    )

                # Validate quantity
                if quantity < 1:
                    return ServiceResult.fail(
                        "Quantity must be at least 1",
                        error_code="INVALID_QUANTITY"
                    )

                # Check if buyer is within the group radius
                distance_km = group.center_point.distance(
                    buyer_location) / 1000

                if distance_km > group.radius_km:
                    return ServiceResult.fail(
                        f"You are {distance_km:.1f}km from the group center (max: {group.radius_km}km)",
                        error_code="OUT_OF_RADIUS"
                    )

                # Validate and reserve stock
                # Deduct stock immediately to prevent overselling (pessimistic locking)
                product = group.product

                if product.stock_quantity < quantity:
                    return ServiceResult.fail(
                        f"Insufficient stock. Product has {product.stock_quantity} units available, you requested {quantity} units",
                        error_code="INSUFFICIENT_STOCK"
                    )

                # Reserve stock by deducting it now
                Product.objects.filter(id=product.id).update(
                    stock_quantity=F('stock_quantity') - quantity
                )

                # Create commitment
                commitment = GroupCommitment.objects.create(
                    group=group,
                    buyer=buyer,
                    quantity=quantity,
                    buyer_location=buyer_location,
                    buyer_postcode=buyer_postcode,
                    stripe_payment_intent_id=payment_intent_id,
                    delivery_address=delivery_address,
                    delivery_notes=delivery_notes or '',
                    status='pending'
                )

                # Update group quantities
                old_quantity = group.current_quantity
                group.current_quantity = F('current_quantity') + quantity
                group.save(update_fields=['current_quantity'])
                group.refresh_from_db()

                # Create update event
                GroupUpdate.objects.create(
                    group=group,
                    event_type='commitment',
                    event_data={
                        'buyer_id': buyer.id,
                        'buyer_name': buyer.get_full_name(),
                        'quantity': quantity,
                        'new_total': group.current_quantity,
                        'target': group.target_quantity
                    }
                )

                # Get current participants count
                participants_count = group.commitments.filter(
                    status='pending').count()

                # WEBSOCKET: Broadcast new commitment notification
                broadcaster.broadcast_new_commitment(
                    group_id=group.id,
                    buyer_name=buyer.get_full_name(),
                    quantity=quantity,
                    new_total=group.current_quantity,
                    participants_count=participants_count
                )

                # WEBSOCKET: Broadcast progress update with full data
                time_remaining = group.expires_at - timezone.now()
                time_remaining_seconds = int(
                    time_remaining.total_seconds()) if time_remaining.total_seconds() > 0 else 0

                broadcaster.broadcast_progress(
                    group_id=group.id,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity,
                    participants_count=participants_count,
                    progress_percent=group.progress_percent,
                    time_remaining_seconds=time_remaining_seconds
                )

                self.log_info(
                    f"User {buyer.id} joined group {group.id}",
                    group_id=group.id,
                    buyer_id=buyer.id,
                    quantity=quantity
                )

            # Check if target reached (outside transaction to prevent lock timeout)
            # Use atomic update to prevent race condition - only one thread will succeed
            if old_quantity < group.target_quantity and group.current_quantity >= group.target_quantity:
                # Atomically try to change status from 'open' to 'active'
                # Only one concurrent request will succeed in this update
                updated_count = BuyingGroup.objects.filter(
                    id=group.id,
                    status='open'
                ).update(status='active')

                # Only process if we were the one to successfully change the status
                if updated_count > 0:
                    group.refresh_from_db()
                    self._handle_target_reached(group)

                    broadcaster.broadcast_threshold_reached(
                        group_id=group.id,
                        threshold_percent=100,
                        current_quantity=group.current_quantity,
                        target_quantity=group.target_quantity
                    )

            return ServiceResult.ok({
                'commitment': commitment,
                'group': group,
                'target_reached': group.current_quantity >= group.target_quantity
            })

        except BuyingGroup.DoesNotExist:
            return ServiceResult.fail(
                "Group not found",
                error_code="GROUP_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error joining group",
                exception=e,
                group_id=group_id
            )
            return ServiceResult.fail(
                "Failed to join group",
                error_code="JOIN_FAILED"
            )

    def leave_group(
        self,
        group_id: int,
        buyer: User,
        reason: Optional[str] = None
    ) -> ServiceResult:
        """
        Allow a buyer to leave/cancel their commitment with WebSocket notification.

        Args:
            group_id: ID of the group to leave
            buyer: User cancelling their commitment
            reason: Optional reason for leaving

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            with transaction.atomic():
                group = BuyingGroup.objects.select_for_update().get(
                    id=group_id)

                # Find active commitment
                commitment = GroupCommitment.objects.filter(
                    group=group,
                    buyer=buyer,
                    status='pending'
                ).first()

                if not commitment:
                    return ServiceResult.fail(
                        "No active commitment found",
                        error_code="NO_COMMITMENT"
                    )

                # Can only leave if group is still open
                if group.status != 'open':
                    return ServiceResult.fail(
                        f"Cannot leave group with status {group.status}",
                        error_code="CANNOT_LEAVE"
                    )

                # Cancel Stripe payment intent if exists
                if commitment.stripe_payment_intent_id:
                    from apps.integrations.services.stripe_service import StripeConnectService
                    stripe_service = StripeConnectService()
                    stripe_service.cancel_payment_intent(
                        commitment.stripe_payment_intent_id
                    )

                # Return reserved stock to inventory
                Product.objects.filter(id=group.product.id).update(
                    stock_quantity=F('stock_quantity') + commitment.quantity
                )

                # Update commitment
                commitment.status = 'cancelled'
                commitment.save(update_fields=['status'])

                # Update group quantity
                old_quantity = group.current_quantity
                group.current_quantity = F(
                    'current_quantity') - commitment.quantity
                group.save(update_fields=['current_quantity'])
                group.refresh_from_db()

                # Create update event
                GroupUpdate.objects.create(
                    group=group,
                    event_type='cancellation',
                    event_data={
                        'buyer_id': buyer.id,
                        'buyer_name': buyer.get_full_name(),
                        'quantity': commitment.quantity,
                        'new_total': group.current_quantity,
                        'reason': reason
                    }
                )

                # Get current participants count
                participants_count = group.commitments.filter(
                    status='pending').count()

                # WEBSOCKET: Broadcast cancellation notification
                broadcaster.broadcast_commitment_cancelled(
                    group_id=group.id,
                    quantity=commitment.quantity,
                    new_total=group.current_quantity,
                    participants_count=participants_count
                )

                # WEBSOCKET: Broadcast progress update with full data
                time_remaining = group.expires_at - timezone.now()
                time_remaining_seconds = int(
                    time_remaining.total_seconds()) if time_remaining.total_seconds() > 0 else 0

                broadcaster.broadcast_progress(
                    group_id=group.id,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity,
                    participants_count=participants_count,
                    progress_percent=group.progress_percent,
                    time_remaining_seconds=time_remaining_seconds
                )

                self.log_info(
                    f"User {buyer.id} left group {group.id}",
                    group_id=group.id,
                    buyer_id=buyer.id,
                    quantity=commitment.quantity
                )

                return ServiceResult.ok({
                    'commitment': commitment,
                    'group': group
                })

        except BuyingGroup.DoesNotExist:
            return ServiceResult.fail(
                "Group not found",
                error_code="GROUP_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error leaving group",
                exception=e,
                group_id=group_id
            )
            return ServiceResult.fail(
                "Failed to leave group",
                error_code="LEAVE_FAILED"
            )

    def get_group_details(self, group_id: int) -> ServiceResult:
        """
        Get detailed information about a buying group.

        Args:
            group_id: ID of the group

        Returns:
            ServiceResult containing group details or error
        """
        try:
            group = BuyingGroup.objects.select_related(
                'product', 'product__vendor'
            ).prefetch_related(
                'commitments'
            ).get(id=group_id)

            # Calculate progress
            progress_percent = (
                group.current_quantity / group.target_quantity * 100
            ) if group.target_quantity > 0 else 0

            # Time remaining
            time_remaining = group.expires_at - timezone.now()
            hours_remaining = max(
                0, int(time_remaining.total_seconds() / 3600))

            # Get recent updates
            recent_updates = GroupUpdate.objects.filter(
                group=group
            ).order_by('-created_at')[:10]

            return ServiceResult.ok({
                'group': group,
                'progress_percent': progress_percent,
                'hours_remaining': hours_remaining,
                'is_active': group.status == 'open' and not group.is_expired,
                'recent_updates': recent_updates,
                'commitment_count': group.commitments.filter(status='pending').count()
            })

        except BuyingGroup.DoesNotExist:
            return ServiceResult.fail(
                "Group not found",
                error_code="GROUP_NOT_FOUND"
            )

    def _handle_target_reached(self, group: BuyingGroup) -> None:
        """
        Handle when a group reaches its target quantity.
        Processes immediately when target is reached.

        Args:
            group: The buying group that reached target
        """
        # Create update event
        GroupUpdate.objects.create(
            group=group,
            event_type='threshold',
            event_data={
                'current_quantity': group.current_quantity,
                'target_quantity': group.target_quantity,
                'message': 'Target quantity reached! Processing orders now.'
            }
        )

        self.log_info(
            f"Group {group.id} reached target quantity - processing immediately",
            group_id=group.id,
            quantity=group.current_quantity
        )

        # Status is already 'active' from atomic update in join_group

        # Create orders immediately
        self._process_successful_group(group)

        # Mark group as completed
        group.status = 'completed'
        group.save(update_fields=['status'])

        self.log_info(
            f"Group {group.id} processed immediately after reaching target",
            group_id=group.id
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

                    # Check if group already reached target and created orders
                    if group.status == 'completed':
                        # Already processed when target was reached - skip
                        continue

                    if group.current_quantity >= group.min_quantity:
                        # Group reached minimum but not target - process now
                        group.status = 'active'
                        # CRITICAL: Save status before processing
                        group.save(update_fields=['status'])
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
        self.log_info(
            f"Processing successful group {group.id}",
            group_id=group.id,
            quantity=group.current_quantity
        )

        # Create orders from all commitments using OrderService
        from apps.orders.services.order_service import OrderService
        order_service = OrderService()

        result = order_service.create_orders_from_successful_group(group.id)

        if result.success:
            self.log_info(
                f"Successfully created orders for group {group.id}",
                group_id=group.id,
                orders_created=result.data['orders_created'],
                orders_failed=result.data['orders_failed']
            )
        else:
            self.log_error(
                f"Failed to create orders for group {group.id}",
                error=result.error,
                group_id=group.id
            )

    def _process_failed_group(self, group: BuyingGroup) -> None:
        """
        Process a failed group (release payment holds, notify users).

        Args:
            group: The failed buying group
        """
        # Cancel all payment intents
        from apps.integrations.services.stripe_service import StripeConnectService
        stripe_service = StripeConnectService()

        pending_commitments = group.commitments.filter(status='pending')

        # Calculate total stock to return
        total_stock_to_return = sum(c.quantity for c in pending_commitments)

        for commitment in pending_commitments:
            # Cancel Stripe payment intent if exists
            # More robust check: ensure it's not empty string or None
            if commitment.stripe_payment_intent_id and commitment.stripe_payment_intent_id.strip():
                cancel_result = stripe_service.cancel_payment_intent(
                    commitment.stripe_payment_intent_id
                )

                if not cancel_result.success:
                    self.log_warning(
                        "Failed to cancel payment intent for commitment",
                        commitment_id=commitment.id,
                        error=cancel_result.error,
                        error_code=cancel_result.error_code
                    )
                    # Continue processing other commitments - don't fail the entire group
            elif commitment.stripe_payment_intent_id == '':
                # Log seeded/test data without payment intent
                self.log_info(
                    "Commitment has empty payment intent ID (likely test data)",
                    commitment_id=commitment.id,
                    group_id=group.id
                )

            # Update commitment status regardless of payment cancellation result
            commitment.status = 'cancelled'
            commitment.save(update_fields=['status'])

        # Return all reserved stock to inventory
        if total_stock_to_return > 0:
            Product.objects.filter(id=group.product.id).update(
                stock_quantity=F('stock_quantity') + total_stock_to_return
            )

        self.log_info(
            f"Processed failed group {group.id}",
            group_id=group.id,
            cancelled_commitments=pending_commitments.count()
        )
