"""
Order service for managing B2B marketplace orders.
Handles order creation, processing, fulfillment, and group buying conversions.
"""
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F, Q, Sum, Count, Avg
from django.utils import timezone

from apps.core.services.base import (
    BaseService, ServiceResult, ValidationError,
    BusinessRuleViolation
)
from apps.orders.models import Order, OrderItem
from apps.vendors.models import Vendor
from apps.products.models import Product
from apps.core.models import User, Address
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.core.utils.websocket_utils import broadcaster


class OrderService(BaseService):
    """
    Service for managing order operations.
    Handles order lifecycle from creation through fulfillment.
    """

    # Business rule constants
    MIN_ORDER_VALUE = Decimal('50.00')
    MAX_ORDER_VALUE = Decimal('10000.00')
    DEFAULT_DELIVERY_FEE = Decimal('5.00')
    FREE_DELIVERY_THRESHOLD = Decimal('150.00')

    # Status transition rules
    VALID_STATUS_TRANSITIONS = {
        'pending': ['paid', 'cancelled'],
        'paid': ['processing', 'cancelled', 'refunded'],
        'processing': ['shipped', 'cancelled', 'refunded'],
        'shipped': ['delivered', 'refunded'],
        'delivered': ['refunded'],
        'cancelled': [],
        'refunded': []
    }

    @transaction.atomic
    def create_order(
        self,
        buyer: User,
        vendor_id: int,
        delivery_address_id: int,
        items: List[Dict[str, Any]],
        delivery_notes: Optional[str] = None,
        group_id: Optional[int] = None
    ) -> ServiceResult:
        """
        Create a new order with items.

        Args:
            buyer: User placing the order
            vendor_id: Vendor ID
            delivery_address_id: Delivery address ID
            items: List of dicts with 'product_id' and 'quantity'
            delivery_notes: Optional delivery instructions
            group_id: Optional buying group ID

        Returns:
            ServiceResult containing created Order or error
        """
        try:
            # Validate vendor
            try:
                vendor = Vendor.objects.get(id=vendor_id, is_approved=True)
            except Vendor.DoesNotExist:
                return ServiceResult.fail(
                    "Vendor not found or not approved",
                    error_code="VENDOR_NOT_FOUND"
                )

            # Validate delivery address
            try:
                address = Address.objects.get(
                    id=delivery_address_id, user=buyer)
            except Address.DoesNotExist:
                return ServiceResult.fail(
                    "Delivery address not found",
                    error_code="ADDRESS_NOT_FOUND"
                )

            # Validate and prepare items
            order_items = []
            subtotal = Decimal('0.00')
            vat_total = Decimal('0.00')

            for item_data in items:
                # Validate product
                try:
                    product = Product.objects.get(
                        id=item_data['product_id'],
                        vendor=vendor,
                        is_active=True
                    )
                except Product.DoesNotExist:
                    return ServiceResult.fail(
                        f"Product {item_data['product_id']} not found or inactive",
                        error_code="PRODUCT_NOT_FOUND"
                    )

                quantity = item_data['quantity']

                # Validate quantity
                if quantity <= 0:
                    return ServiceResult.fail(
                        f"Invalid quantity for product {product.name}",
                        error_code="INVALID_QUANTITY"
                    )

                # Check stock
                if product.stock_quantity < quantity:
                    return ServiceResult.fail(
                        f"Insufficient stock for {product.name} (available: {product.stock_quantity})",
                        error_code="INSUFFICIENT_STOCK"
                    )

                # Calculate prices
                unit_price = product.price
                item_subtotal = unit_price * quantity
                item_vat = item_subtotal * product.vat_rate

                # Check for group buying discount
                discount_amount = Decimal('0.00')
                if group_id:
                    group_result = self._apply_group_discount(
                        group_id,
                        product.id,
                        item_subtotal
                    )
                    if group_result.success:
                        discount_amount = group_result.data['discount_amount']
                        item_subtotal -= discount_amount
                        item_vat = item_subtotal * product.vat_rate  # Recalculate VAT

                order_items.append({
                    'product': product,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'total_price': item_subtotal,
                    'discount_amount': discount_amount,
                    'vat_amount': item_vat
                })

                subtotal += item_subtotal
                vat_total += item_vat

            # Check minimum order value
            if subtotal < vendor.min_order_value:
                return ServiceResult.fail(
                    f"Order total must be at least £{vendor.min_order_value}",
                    error_code="BELOW_MINIMUM"
                )

            # Check maximum order value
            if subtotal > self.MAX_ORDER_VALUE:
                return ServiceResult.fail(
                    f"Order total cannot exceed £{self.MAX_ORDER_VALUE}",
                    error_code="EXCEEDS_MAXIMUM"
                )

            # Calculate delivery fee
            delivery_fee = self._calculate_delivery_fee(
                subtotal, vendor, address)

            # Calculate total
            total = subtotal + vat_total + delivery_fee

            # Calculate marketplace fee and vendor payout
            marketplace_fee = subtotal * vendor.commission_rate
            vendor_payout = total - marketplace_fee

            # Create order
            order = Order.objects.create(
                buyer=buyer,
                vendor=vendor,
                delivery_address=address,
                group_id=group_id,
                subtotal=subtotal,
                vat_amount=vat_total,
                delivery_fee=delivery_fee,
                total=total,
                marketplace_fee=marketplace_fee,
                vendor_payout=vendor_payout,
                delivery_notes=delivery_notes or '',
                status='pending'
            )

            # Create order items
            for item_data in order_items:
                OrderItem.objects.create(
                    order=order,
                    product=item_data['product'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    total_price=item_data['total_price'],
                    discount_amount=item_data['discount_amount']
                )

                # Reserve stock
                Product.objects.filter(id=item_data['product'].id).update(
                    stock_quantity=F('stock_quantity') - item_data['quantity']
                )

            self.log_info(
                f"Created order {order.reference_number}",
                order_id=order.id,
                buyer_id=buyer.id,
                vendor_id=vendor.id,
                total=float(total)
            )

            return ServiceResult.ok(order)

        except Exception as e:
            self.log_error(
                f"Error creating order",
                exception=e,
                buyer_id=buyer.id,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to create order",
                error_code="CREATE_FAILED"
            )

    def create_order_from_group(
        self,
        group_id: int,
        commitment_id: int
    ) -> ServiceResult:
        """
        Create an order from a successful group buying commitment.

        Args:
            group_id: BuyingGroup ID
            commitment_id: GroupCommitment ID

        Returns:
            ServiceResult containing created Order or error
        """
        try:
            # Get commitment with related data
            try:
                commitment = GroupCommitment.objects.select_related(
                    'group__product__vendor',
                    'buyer'
                ).get(id=commitment_id, group_id=group_id)
            except GroupCommitment.DoesNotExist:
                return ServiceResult.fail(
                    "Commitment not found",
                    error_code="COMMITMENT_NOT_FOUND"
                )

            # Validate commitment status
            if commitment.status != 'pending':
                return ServiceResult.fail(
                    "Commitment already processed",
                    error_code="ALREADY_PROCESSED"
                )

            group = commitment.group

            # Validate group status
            if group.status not in ['active', 'completed']:
                return ServiceResult.fail(
                    "Group not ready for order creation",
                    error_code="GROUP_NOT_READY"
                )

            # Get buyer's default address
            address = Address.objects.filter(
                user=commitment.buyer,
                is_default=True
            ).first()

            if not address:
                # Use first available address
                address = Address.objects.filter(user=commitment.buyer).first()

            if not address:
                return ServiceResult.fail(
                    "No delivery address found for buyer",
                    error_code="NO_ADDRESS"
                )

            # Calculate prices with group discount
            product = group.product
            quantity = commitment.quantity

            unit_price = product.price
            discount_multiplier = 1 - (group.discount_percent / 100)
            discounted_price = unit_price * discount_multiplier
            subtotal = discounted_price * quantity
            discount_amount = (unit_price * quantity) - subtotal
            vat_amount = subtotal * product.vat_rate

            # Calculate delivery fee
            vendor = product.vendor
            delivery_fee = self._calculate_delivery_fee(
                subtotal, vendor, address)

            # Calculate total
            total = subtotal + vat_amount + delivery_fee

            # Calculate marketplace fee and vendor payout
            marketplace_fee = subtotal * vendor.commission_rate
            vendor_payout = total - marketplace_fee

            # Create order with transaction
            with transaction.atomic():
                # Create order
                order = Order.objects.create(
                    buyer=commitment.buyer,
                    vendor=vendor,
                    delivery_address=address,
                    group=group,
                    subtotal=subtotal,
                    vat_amount=vat_amount,
                    delivery_fee=delivery_fee,
                    total=total,
                    marketplace_fee=marketplace_fee,
                    vendor_payout=vendor_payout,
                    delivery_notes=f"Group buying order - {group.area_name}",
                    status='pending',
                    stripe_payment_intent_id=commitment.stripe_payment_intent_id
                )

                # Create order item
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=discounted_price,
                    total_price=subtotal,
                    discount_amount=discount_amount
                )

                # Update commitment status
                commitment.status = 'confirmed'
                commitment.save(update_fields=['status'])

                # Link commitment to order
                commitment.order = order
                commitment.save(update_fields=['status', 'order'])

                # Capture payment
                from apps.integrations.services.stripe_service import StripeConnectService
                stripe_service = StripeConnectService()

                capture_result = stripe_service.capture_group_payment(
                    commitment.stripe_payment_intent_id
                )

                if capture_result.success:
                    order.status = 'paid'
                    order.paid_at = timezone.now()
                    order.save(update_fields=['status', 'paid_at'])

                self.log_info(
                    f"Created order from group commitment",
                    order_id=order.id,
                    group_id=group_id,
                    commitment_id=commitment_id
                )

                return ServiceResult.ok(order)

        except Exception as e:
            self.log_error(
                f"Error creating order from group",
                exception=e,
                group_id=group_id,
                commitment_id=commitment_id
            )
            return ServiceResult.fail(
                "Failed to create order from group",
                error_code="CREATE_FAILED"
            )

    def create_orders_from_successful_group(self, group_id: int) -> ServiceResult:
        """
        Create orders for all commitments in a successful buying group.
        Broadcasts real-time updates as each order is created.

        Args:
            group_id: ID of the successful buying group

        Returns:
            ServiceResult containing summary of created orders
        """
        from apps.core.utils.websocket_utils import broadcaster  # Import at top of file

        try:
            # Get the group
            try:
                group = BuyingGroup.objects.select_related(
                    'product__vendor'
                ).get(id=group_id)
            except BuyingGroup.DoesNotExist:
                return ServiceResult.fail(
                    f"Group {group_id} not found",
                    error_code="GROUP_NOT_FOUND"
                )

            # Validate group status
            if group.status not in ['active', 'completed']:
                return ServiceResult.fail(
                    f"Group status must be active or completed, got {group.status}",
                    error_code="INVALID_STATUS"
                )

            # Get all pending commitments
            commitments = GroupCommitment.objects.filter(
                group=group,
                status='pending'
            ).select_related('buyer')

            if not commitments.exists():
                return ServiceResult.ok({
                    'message': 'No pending commitments to process',
                    'orders_created': 0,
                    'orders_failed': 0
                })

            # Process statistics
            orders_created = []
            orders_failed = []
            total_revenue = Decimal('0.00')

            # Process each commitment
            for i, commitment in enumerate(commitments, 1):
                try:
                    # Broadcast progress for each order being created
                    broadcaster.broadcast_progress(
                        group_id=group_id,
                        current_quantity=group.current_quantity,
                        target_quantity=group.target_quantity,
                        participants_count=commitments.count(),
                        progress_percent=100.0,  # Group is complete
                        time_remaining_seconds=0
                    )

                    # Create order from commitment
                    result = self.create_order_from_group(
                        group_id=group_id,
                        commitment_id=commitment.id
                    )

                    if result.success:
                        order = result.data
                        orders_created.append(order.id)
                        total_revenue += order.total

                        # Log success
                        self.log_info(
                            f"Created order {order.reference_number} for commitment {commitment.id}",
                            order_id=order.id,
                            buyer_id=commitment.buyer.id,
                            progress=f"{i}/{commitments.count()}"
                        )

                        # WEBSOCKET: Notify the specific buyer their order is ready
                        # This would be sent to a user-specific channel
                        # For now, we'll include it in group updates
                        from apps.buying_groups.models import GroupUpdate
                        GroupUpdate.objects.create(
                            group=group,
                            event_type='commitment',
                            event_data={
                                'message': f'Order created for {commitment.buyer.username}',
                                'order_id': order.id,
                                'order_reference': order.reference_number,
                                'buyer_id': commitment.buyer.id
                            }
                        )

                    else:
                        orders_failed.append({
                            'commitment_id': commitment.id,
                            'buyer_id': commitment.buyer.id,
                            'error': result.error
                        })

                        self.log_error(
                            f"Failed to create order for commitment {commitment.id}",
                            error=result.error,
                            buyer_id=commitment.buyer.id
                        )

                except Exception as e:
                    orders_failed.append({
                        'commitment_id': commitment.id,
                        'buyer_id': commitment.buyer.id,
                        'error': str(e)
                    })

                    self.log_error(
                        f"Exception creating order for commitment {commitment.id}",
                        exception=e,
                        buyer_id=commitment.buyer.id
                    )

            # Update group status if all orders created
            if len(orders_created) == commitments.count():
                group.status = 'completed'
                group.save(update_fields=['status'])

                # WEBSOCKET: Broadcast completion
                broadcaster.broadcast_status_change(
                    group_id=group_id,
                    old_status='active',
                    new_status='completed',
                    reason=f'All {len(orders_created)} orders created successfully!'
                )

            # Log summary
            self.log_info(
                f"Processed group {group_id} orders",
                group_id=group_id,
                total_commitments=commitments.count(),
                orders_created=len(orders_created),
                orders_failed=len(orders_failed),
                total_revenue=float(total_revenue)
            )

            return ServiceResult.ok({
                'group_id': group_id,
                'total_commitments': commitments.count(),
                'orders_created': len(orders_created),
                'orders_failed': len(orders_failed),
                'failed_details': orders_failed,
                'total_revenue': total_revenue,
                'status': 'complete' if len(orders_failed) == 0 else 'partial'
            })

        except Exception as e:
            self.log_error(
                f"Error processing successful group {group_id}",
                exception=e,
                group_id=group_id
            )
            return ServiceResult.fail(
                "Failed to process group orders",
                error_code="PROCESSING_FAILED"
            )

    def update_order_status(
        self,
        order_id: int,
        new_status: str,
        user: User,
        notes: Optional[str] = None
    ) -> ServiceResult:
        """
        Update order status with validation.

        Args:
            order_id: Order ID
            new_status: New status to set
            user: User making the change
            notes: Optional notes about the change

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            # Get order
            order = Order.objects.select_related('vendor').get(id=order_id)

            # Check permissions
            if not self._can_update_order(order, user):
                return ServiceResult.fail(
                    "You don't have permission to update this order",
                    error_code="PERMISSION_DENIED"
                )

            # Validate status transition
            current_status = order.status

            if new_status not in self.VALID_STATUS_TRANSITIONS.get(current_status, []):
                return ServiceResult.fail(
                    f"Cannot transition from {current_status} to {new_status}",
                    error_code="INVALID_TRANSITION"
                )

            # Update status
            order.status = new_status

            # Set timestamps based on status
            if new_status == 'paid':
                order.paid_at = timezone.now()
            elif new_status == 'delivered':
                order.delivered_at = timezone.now()

            order.save()

            # Handle status-specific actions
            if new_status == 'cancelled':
                self._handle_order_cancellation(order)
            elif new_status == 'refunded':
                self._handle_order_refund(order)

            self.log_info(
                f"Updated order {order.reference_number} status",
                order_id=order.id,
                old_status=current_status,
                new_status=new_status,
                user_id=user.id,
                notes=notes
            )

            return ServiceResult.ok({
                'order_id': order.id,
                'reference': order.reference_number,
                'old_status': current_status,
                'new_status': new_status
            })

        except Order.DoesNotExist:
            return ServiceResult.fail(
                f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error updating order status",
                exception=e,
                order_id=order_id,
                new_status=new_status
            )
            return ServiceResult.fail(
                "Failed to update order status",
                error_code="UPDATE_FAILED"
            )

    def process_payment(self, order_id: int, payment_method_id: str) -> ServiceResult:
        """
        Process payment for an order.

        Args:
            order_id: Order ID
            payment_method_id: Stripe payment method ID

        Returns:
            ServiceResult containing payment confirmation or error
        """
        try:
            order = Order.objects.select_related(
                'vendor', 'buyer').get(id=order_id)

            if order.status != 'pending':
                return ServiceResult.fail(
                    "Order is not pending payment",
                    error_code="INVALID_STATUS"
                )

            # Process payment through Stripe
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()

            payment_result = stripe_service.process_marketplace_order(order)

            if not payment_result.success:
                return payment_result

            # Update order status
            order.status = 'paid'
            order.paid_at = timezone.now()
            order.save(update_fields=['status', 'paid_at'])

            self.log_info(
                f"Processed payment for order {order.reference_number}",
                order_id=order.id,
                amount=float(order.total)
            )

            # TODO: Send order confirmation email
            # TODO: Notify vendor of new order

            return ServiceResult.ok({
                'order_id': order.id,
                'reference': order.reference_number,
                'payment_status': 'succeeded',
                'amount': order.total
            })

        except Order.DoesNotExist:
            return ServiceResult.fail(
                f"Order {order_id} not found",
                error_code="ORDER_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error processing payment",
                exception=e,
                order_id=order_id
            )
            return ServiceResult.fail(
                "Payment processing failed",
                error_code="PAYMENT_FAILED"
            )

    def get_order_analytics(
        self,
        vendor_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> ServiceResult:
        """
        Get order analytics for a vendor or platform.

        Args:
            vendor_id: Optional vendor ID for vendor-specific stats
            date_from: Start date for analytics
            date_to: End date for analytics

        Returns:
            ServiceResult containing analytics data
        """
        try:
            # Build query
            query = Order.objects.all()

            if vendor_id:
                query = query.filter(vendor_id=vendor_id)

            if date_from:
                query = query.filter(created_at__gte=date_from)

            if date_to:
                query = query.filter(created_at__lte=date_to)

            # Calculate statistics
            stats = query.aggregate(
                total_orders=Count('id'),
                total_revenue=Sum('total'),
                total_commission=Sum('marketplace_fee'),
                average_order_value=Avg('total'),
                total_items=Sum('items__quantity')
            )

            # Status breakdown
            status_breakdown = dict(
                query.values('status').annotate(
                    count=Count('id')
                ).values_list('status', 'count')
            )

            # Top products
            top_products = OrderItem.objects.filter(
                order__in=query
            ).values(
                'product__id',
                'product__name'
            ).annotate(
                total_quantity=Sum('quantity'),
                total_revenue=Sum('total_price')
            ).order_by('-total_revenue')[:10]

            # Daily revenue (last 30 days)
            thirty_days_ago = timezone.now() - timedelta(days=30)
            daily_revenue = query.filter(
                created_at__gte=thirty_days_ago,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).extra(
                select={'day': 'date(created_at)'}
            ).values('day').annotate(
                revenue=Sum('total'),
                orders=Count('id')
            ).order_by('day')

            return ServiceResult.ok({
                'summary': {
                    'total_orders': stats['total_orders'] or 0,
                    'total_revenue': float(stats['total_revenue'] or 0),
                    'total_commission': float(stats['total_commission'] or 0),
                    'average_order_value': float(stats['average_order_value'] or 0),
                    'total_items': stats['total_items'] or 0
                },
                'status_breakdown': status_breakdown,
                'top_products': list(top_products),
                'daily_revenue': list(daily_revenue)
            })

        except Exception as e:
            self.log_error(
                f"Error generating order analytics",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to generate analytics",
                error_code="ANALYTICS_FAILED"
            )

    def _calculate_delivery_fee(
        self,
        subtotal: Decimal,
        vendor: Vendor,
        address: Address
    ) -> Decimal:
        """
        Calculate delivery fee based on order value and distance.

        Args:
            subtotal: Order subtotal
            vendor: Vendor instance
            address: Delivery address

        Returns:
            Delivery fee amount
        """
        # Free delivery for orders over threshold
        if subtotal >= self.FREE_DELIVERY_THRESHOLD:
            return Decimal('0.00')

        # Calculate distance-based fee if locations available
        if vendor.location and address.location:
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()

            distance_km = geo_service.calculate_distance(
                vendor.location,
                address.location
            )

            # £5 base + £1 per km over 3km
            if distance_km > 3:
                return self.DEFAULT_DELIVERY_FEE + Decimal(str(distance_km - 3))

        return self.DEFAULT_DELIVERY_FEE

    def _apply_group_discount(
        self,
        group_id: int,
        product_id: int,
        original_price: Decimal
    ) -> ServiceResult:
        """
        Apply group buying discount to a price.

        Args:
            group_id: BuyingGroup ID
            product_id: Product ID
            original_price: Original price before discount

        Returns:
            ServiceResult containing discount amount
        """
        try:
            group = BuyingGroup.objects.get(
                id=group_id,
                product_id=product_id,
                status__in=['active', 'completed']
            )

            discount_amount = original_price * (group.discount_percent / 100)

            return ServiceResult.ok({
                'discount_amount': discount_amount,
                'discount_percent': group.discount_percent
            })

        except BuyingGroup.DoesNotExist:
            return ServiceResult.ok({
                'discount_amount': Decimal('0.00'),
                'discount_percent': Decimal('0.00')
            })

    def _can_update_order(self, order: Order, user: User) -> bool:
        """
        Check if user can update an order.

        Args:
            order: Order instance
            user: User attempting update

        Returns:
            True if allowed, False otherwise
        """
        # Buyer can cancel their own pending orders
        if order.buyer == user and order.status == 'pending':
            return True

        # Vendor can update their own orders
        if hasattr(user, 'vendor') and order.vendor == user.vendor:
            return True

        # Staff can update any order
        if user.is_staff:
            return True

        return False

    def _handle_order_cancellation(self, order: Order) -> None:
        """
        Handle order cancellation side effects.

        Args:
            order: Order being cancelled
        """
        # Return stock to inventory
        for item in order.items.all():
            Product.objects.filter(id=item.product.id).update(
                stock_quantity=F('stock_quantity') + item.quantity
            )

        # Cancel payment if exists
        if order.stripe_payment_intent_id:
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()
            stripe_service.cancel_payment_intent(
                order.stripe_payment_intent_id)

        self.log_info(
            f"Handled cancellation for order {order.reference_number}",
            order_id=order.id
        )

    def _handle_order_refund(self, order: Order) -> None:
        """
        Handle order refund side effects.

        Args:
            order: Order being refunded
        """
        # Process refund through Stripe
        if order.stripe_payment_intent_id:
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()
            stripe_service.process_refund(order.id)

        # Return stock if order was never shipped
        if order.status in ['paid', 'processing']:
            for item in order.items.all():
                Product.objects.filter(id=item.product.id).update(
                    stock_quantity=F('stock_quantity') + item.quantity
                )

        self.log_info(
            f"Handled refund for order {order.reference_number}",
            order_id=order.id
        )
