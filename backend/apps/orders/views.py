"""
ViewSet implementations for order operations.
Handles order creation, processing, and fulfillment.
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

from .models import Order, OrderItem, Cart, CartItem
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
    OrderStatusUpdateSerializer,
    CartSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CheckoutSerializer
)
from .services.order_service import OrderService
from apps.products.models import Product
from apps.vendors.models import Vendor


@extend_schema_view(
    list=extend_schema(
        summary="List orders",
        description="""
        Retrieve orders based on user role and permissions.
 
        **Access Control:**
        - Buyers: See only their own orders
        - Vendors: See orders from their vendor account
        - Staff/Admin: See all orders
 
        **Filtering:**
        - Filter by order status
        - Filter by date range (date_from, date_to)
        - Filter by vendor ID (buyers/staff only)
 
        **Permissions:** Authenticated users only
        """,
        parameters=[
            OpenApiParameter(
                name='status',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by order status',
                examples=[
                    OpenApiExample('Pending orders', value='pending'),
                    OpenApiExample('Paid orders', value='paid'),
                    OpenApiExample('Completed orders', value='completed'),
                ]
            ),
            OpenApiParameter(
                name='date_from',
                type=Types.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter orders from date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='date_to',
                type=Types.DATE,
                location=OpenApiParameter.QUERY,
                description='Filter orders to date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='vendor',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by vendor ID'
            ),
        ],
        tags=['Orders']
    ),
    retrieve=extend_schema(
        summary="Get order details",
        description="""
        Retrieve detailed information about a specific order.
 
        **Includes:**
        - All order items with product details
        - Vendor and buyer information
        - Delivery address
        - Payment status and amounts
        - Order timeline and status history
 
        **Permissions:** Order owner (buyer/vendor) or admin
        """,
        tags=['Orders']
    ),
    create=extend_schema(
        summary="Create a new order",
        description="""
        Create a new order from buyer to vendor.
 
        **Process:**
        1. Validates all products belong to same vendor
        2. Checks product availability and stock
        3. Validates delivery address
        4. Calculates totals (subtotal, VAT, delivery fee)
        5. Creates order with 'pending' status
        6. Reserves stock
 
        **Example Request:**
```json
        {
            "vendor": 5,
            "delivery_address": 12,
            "items": [
                {"product": 15, "quantity": 3},
                {"product": 18, "quantity": 2}
            ],
            "delivery_notes": "Ring doorbell",
            "group": 7
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=OrderCreateSerializer,
        responses={201: OrderDetailSerializer},
        tags=['Orders']
    ),
    update=extend_schema(
        summary="Update order (admin only)",
        description="""
        Update order details (admin only).
 
        **Permissions:** Admin/staff only
        """,
        tags=['Orders']
    ),
    partial_update=extend_schema(
        summary="Partially update order (admin only)",
        description="""
        Partially update order fields (admin only).
 
        **Permissions:** Admin/staff only
        """,
        tags=['Orders']
    ),
    destroy=extend_schema(
        summary="Delete order (admin only)",
        description="""
        Delete an order (admin only). Consider using cancel instead.
 
        **Permissions:** Admin/staff only
        """,
        tags=['Orders']
    ),
)
class OrderViewSet(viewsets.ModelViewSet):
    """
    ViewSet for order operations.
    Handles order lifecycle from creation to fulfillment.
    """
    queryset = Order.objects.all()
    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]
    service = OrderService()

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return OrderDetailSerializer
        elif self.action == 'create':
            return OrderCreateSerializer
        elif self.action in ['update_status', 'partial_update']:
            return OrderStatusUpdateSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        Filter orders based on user role and parameters.
        """
        queryset = super().get_queryset().select_related(
            'vendor', 'buyer', 'delivery_address', 'group'
        ).prefetch_related('items__product')

        user = self.request.user

        # Filter based on user role
        if user.is_staff:
            # Staff can see all orders
            pass
        elif hasattr(user, 'vendor'):
            # Vendors see their own orders
            queryset = queryset.filter(vendor=user.vendor)
        else:
            # Buyers see only their orders
            queryset = queryset.filter(buyer=user)

        # Status filter
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Date range filter
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        # Vendor filter (for buyers/staff)
        vendor_id = self.request.query_params.get('vendor')
        if vendor_id and (user.is_staff or not hasattr(user, 'vendor')):
            queryset = queryset.filter(vendor_id=vendor_id)

        return queryset.order_by('-created_at')

    def create(self, request, *args, **kwargs):
        """Override create to use different serializers for input/output."""
        # Use OrderCreateSerializer for validation
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Use OrderDetailSerializer for the response
        output_serializer = OrderDetailSerializer(serializer.instance)
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        """Create order using service layer."""
        # Don't pop items - keep them for serializer
        items_data = [
            {
                'product_id': item['product'].id,
                'quantity': item['quantity']
            }
            for item in serializer.validated_data.get('items', [])
        ]

        result = self.service.create_order(
            buyer=self.request.user,
            vendor_id=serializer.validated_data['vendor'].id,
            delivery_address_id=serializer.validated_data['delivery_address'].id,
            items=items_data,
            delivery_notes=serializer.validated_data.get('delivery_notes'),
            group_id=serializer.validated_data.get(
                'group').id if serializer.validated_data.get('group') else None
        )

        if not result.success:
            # Raise validation error instead of returning Response
            raise ValidationError({
                'error': result.error,
                'error_code': result.error_code
            })

        # Set the created order as the serializer instance
        serializer.instance = result.data

    @extend_schema(
        summary="Update order status",
        description="""
        Update the status of an order through its lifecycle.
 
        **Status Flow:**
        - pending → paid → processing → shipped → delivered → completed
        - Any status → cancelled (with restrictions)
 
        **Permission Rules:**
        - Buyers: Can only cancel pending orders
        - Vendors: Can update their own orders
        - Staff/Admin: Can update any order
 
        **Example Request:**
```json
        {
            "status": "shipped",
            "notes": "Dispatched via Royal Mail"
        }
```
 
        **Permissions:** Order owner or admin
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'enum': ['pending', 'paid', 'processing', 'shipped', 'delivered', 'completed', 'cancelled']},
                    'notes': {'type': 'string', 'description': 'Optional status update notes'}
                },
                'required': ['status']
            }
        },
        responses={200: OrderDetailSerializer},
        tags=['Orders']
    )
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """
        Update order status.
        POST /api/orders/{id}/update_status/
        """
        order = self.get_object()
        new_status = request.data.get('status')
        notes = request.data.get('notes')

        if not new_status:
            return Response({
                'error': 'status field is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # CHECK PERMISSIONS FIRST - before calling service
        # Buyers can only cancel pending orders
        if order.buyer == request.user:
            if order.status != 'pending' or new_status != 'cancelled':
                return Response({
                    'error': 'You can only cancel pending orders'
                }, status=status.HTTP_403_FORBIDDEN)
        # Vendors can update their own orders
        elif hasattr(request.user, 'vendor') and order.vendor == request.user.vendor:
            pass  # Allowed
        # Staff can update any order
        elif request.user.is_staff:
            pass  # Allowed
        else:
            return Response({
                'error': 'You don\'t have permission to update this order'
            }, status=status.HTTP_403_FORBIDDEN)

        result = self.service.update_order_status(
            order_id=order.id,
            new_status=new_status,
            user=request.user,
            notes=notes
        )

        if result.success:
            order.refresh_from_db()
            return Response({
                'message': f'Order status updated to {new_status}',
                'order': OrderDetailSerializer(order).data
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Process payment for an order",
        description="""
        Process payment using Stripe payment method.
 
        **Process:**
        1. Validates order is in 'pending' status
        2. Creates Stripe payment intent
        3. Charges payment method
        4. Updates order status to 'paid'
        5. Notifies vendor
 
        **Example Request:**
```json
        {
            "payment_method_id": "pm_xxx"
        }
```
 
        **Permissions:** Order buyer only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'payment_method_id': {'type': 'string', 'description': 'Stripe payment method ID'}
                },
                'required': ['payment_method_id']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'payment_status': {'type': 'string'},
                    'order': {'type': 'object'}
                }
            }
        },
        tags=['Orders']
    )
    @action(detail=True, methods=['post'])
    def process_payment(self, request, pk=None):
        """
        Process payment for an order.
        POST /api/orders/{id}/process_payment/
        """
        order = self.get_object()

        # Check permission
        if order.buyer != request.user:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        payment_method_id = request.data.get('payment_method_id')

        if not payment_method_id:
            return Response({
                'error': 'payment_method_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.process_payment(
            order_id=order.id,
            payment_method_id=payment_method_id
        )

        if result.success:
            return Response({
                'message': 'Payment processed successfully',
                'payment_status': result.data['payment_status'],
                'order': OrderDetailSerializer(order.refresh_from_db()).data
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Cancel an order",
        description="""
        Cancel an order and process refund if payment was made.
 
        **Cancellation Rules:**
        - Can only cancel orders in 'pending' or 'paid' status
        - Orders in 'processing' or later stages require admin approval
        - Full refund issued for paid orders
        - Stock is released back to inventory
 
        **Example Request:**
```json
        {
            "reason": "Changed my mind"
        }
```
 
        **Permissions:** Order buyer or admin
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'reason': {'type': 'string', 'description': 'Reason for cancellation'}
                }
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Orders']
    )
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an order.
        POST /api/orders/{id}/cancel/
        """
        order = self.get_object()
        reason = request.data.get('reason')

        # Check if order can be cancelled
        if not order.can_cancel:
            return Response({
                'error': 'Order cannot be cancelled in its current status'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.update_order_status(
            order_id=order.id,
            new_status='cancelled',
            user=request.user,
            notes=reason
        )

        if result.success:
            return Response({
                'message': 'Order cancelled successfully'
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Request a refund for an order",
        description="""
        Request full or partial refund for a completed order.
 
        **Refund Reasons:**
        - requested_by_customer: Customer request
        - duplicate: Duplicate charge
        - fraudulent: Fraudulent transaction
 
        **Process:**
        1. Validates order is paid and eligible for refund
        2. Creates Stripe refund
        3. Updates order payment status
        4. Notifies buyer and vendor
 
        **Example Request:**
```json
        {
            "amount": 25.50,
            "reason": "requested_by_customer"
        }
```
 
        **Permissions:** Order buyer or admin
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'amount': {'type': 'number', 'format': 'decimal', 'description': 'Refund amount (optional - full refund if not provided)'},
                    'reason': {'type': 'string', 'description': 'Refund reason'}
                }
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'refund_id': {'type': 'string'},
                    'amount': {'type': 'number'}
                }
            }
        },
        tags=['Orders']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def request_refund(self, request, pk=None):
        """
        Request a refund for an order.
        POST /api/orders/{id}/request_refund/
        """
        order = self.get_object()

        # Check permission
        if order.buyer != request.user and not request.user.is_staff:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        amount = request.data.get('amount')  # Optional partial refund
        reason = request.data.get('reason', 'requested_by_customer')

        from apps.integrations.services.stripe_service import StripeConnectService
        stripe_service = StripeConnectService()

        result = stripe_service.process_refund(
            order_id=order.id,
            amount=amount,
            reason=reason
        )

        if result.success:
            return Response({
                'message': 'Refund processed successfully',
                'refund_id': result.data['refund_id'],
                'amount': result.data['amount']
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get order analytics",
        description="""
        Retrieve order analytics and metrics for reporting.
 
        **Metrics Included:**
        - Total orders count by status
        - Revenue totals and trends
        - Average order value
        - Top selling products
        - Order fulfillment rates
        - Payment success rates
 
        **Access:**
        - Vendors: See only their own analytics
        - Staff: See all or filter by vendor
 
        **Query Parameters:**
        - date_from: Start date (default: 30 days ago)
        - date_to: End date (default: today)
        - vendor_id: Filter by vendor (staff only)
 
        **Permissions:** Vendor or admin only
        """,
        parameters=[
            OpenApiParameter(
                name='date_from',
                type=Types.DATE,
                location=OpenApiParameter.QUERY,
                description='Analytics start date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='date_to',
                type=Types.DATE,
                location=OpenApiParameter.QUERY,
                description='Analytics end date (YYYY-MM-DD)'
            ),
            OpenApiParameter(
                name='vendor_id',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by vendor ID (staff only)'
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'total_orders': {'type': 'integer'},
                    'total_revenue': {'type': 'number'},
                    'average_order_value': {'type': 'number'},
                    'orders_by_status': {'type': 'object'},
                    'top_products': {'type': 'array'}
                }
            }
        },
        tags=['Orders']
    )
    @action(detail=False, methods=['get'])
    def analytics(self, request):
        """
        Get order analytics.
        GET /api/orders/analytics/?date_from=2024-01-01&date_to=2024-12-31
        """
        # Permission check - vendors see their own, staff sees all
        if not hasattr(request.user, 'vendor') and not request.user.is_staff:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        vendor_id = None
        if hasattr(request.user, 'vendor'):
            vendor_id = request.user.vendor.id
        elif request.user.is_staff:
            vendor_id = request.query_params.get('vendor_id')

        # Parse dates
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if date_from:
            date_from = datetime.fromisoformat(date_from)
        else:
            date_from = timezone.now() - timedelta(days=30)

        if date_to:
            date_to = datetime.fromisoformat(date_to)
        else:
            date_to = timezone.now()

        result = self.service.get_order_analytics(
            vendor_id=int(vendor_id) if vendor_id else None,
            date_from=date_from,
            date_to=date_to
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get pending orders for vendor",
        description="""
        Retrieve pending and processing orders requiring vendor attention.
 
        **Filters:**
        - Orders with status 'paid' or 'processing'
        - Only for the authenticated vendor
        - Ordered by creation date
 
        **Use Cases:**
        - Vendor dashboard
        - Order fulfillment queue
        - Urgent action items
 
        **Permissions:** Vendor account required
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'orders': {'type': 'array'}
                }
            }
        },
        tags=['Orders']
    )
    @action(detail=False, methods=['get'])
    def pending_orders(self, request):
        """
        Get pending orders for vendor dashboard.
        GET /api/orders/pending_orders/
        """
        if not hasattr(request.user, 'vendor'):
            return Response({
                'error': 'Vendor account required'
            }, status=status.HTTP_403_FORBIDDEN)

        orders = self.get_queryset().filter(
            vendor=request.user.vendor,
            status__in=['paid', 'processing']
        )

        serializer = OrderListSerializer(orders, many=True)
        return Response({
            'count': orders.count(),
            'orders': serializer.data
        })


@extend_schema(tags=['Cart'])
class CartViewSet(viewsets.ViewSet):
    """
    ViewSet for shopping cart operations.
    Handles cart management and checkout.
    """
    permission_classes = [IsAuthenticated]

    def get_or_create_cart(self, user):
        """Get or create cart for user."""
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    @extend_schema(
        summary="Get user's shopping cart",
        description="""
        Retrieve the authenticated user's shopping cart with all items.
 
        **Includes:**
        - All cart items with product details
        - Individual item subtotals and VAT
        - Cart total with VAT
        - Items count
        - Organized by vendor
 
        **Permissions:** Authenticated users only
        """,
        responses={200: CartSerializer},
        tags=['Cart']
    )
    def list(self, request):
        """
        Get user's cart with all items.
        GET /api/v1/cart/
        """
        cart = self.get_or_create_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    @extend_schema(
        summary="Add item to cart",
        description="""
        Add a product to cart or update quantity if it already exists.
 
        **Process:**
        1. Validates product exists and is available
        2. Checks stock availability
        3. If item exists in cart, increases quantity
        4. If new item, adds to cart
        5. Returns updated cart item
 
        **Example Request:**
```json
        {
            "product_id": 15,
            "quantity": 2
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'product_id': {'type': 'integer', 'description': 'Product ID to add'},
                    'quantity': {'type': 'integer', 'description': 'Quantity to add'}
                },
                'required': ['product_id', 'quantity']
            }
        },
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'item': {'type': 'object'},
                    'cart_items_count': {'type': 'integer'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """
        Add item to cart or update quantity if exists.
        POST /api/v1/cart/add_item/
        Body: { "product_id": 1, "quantity": 2 }
        """
        cart = self.get_or_create_cart(request.user)

        serializer = CartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']

        # Check if item already in cart
        existing_item = CartItem.objects.filter(
            cart=cart,
            product_id=product_id
        ).first()

        if existing_item:
            # Update quantity
            existing_item.quantity += quantity

            # Validate against stock
            product = existing_item.product
            if existing_item.quantity > product.stock_quantity:
                return Response({
                    'error': f'Only {product.stock_quantity} units available'
                }, status=status.HTTP_400_BAD_REQUEST)

            existing_item.save()
            item = existing_item
            message = f'Updated {product.name} quantity to {existing_item.quantity}'
        else:
            # Create new item
            product = Product.objects.get(id=product_id)
            item = CartItem.objects.create(
                cart=cart,
                product=product,
                quantity=quantity
            )
            message = f'Added {product.name} to cart'

        return Response({
            'message': message,
            'item': CartItemSerializer(item).data,
            'cart_items_count': cart.items_count
        }, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Update cart item quantity",
        description="""
        Update the quantity of an existing cart item.
 
        **Validation:**
        - Validates item belongs to user's cart
        - Checks new quantity against stock availability
        - Prevents quantity below 1
 
        **Example Request:**
```json
        {
            "item_id": 23,
            "quantity": 5
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'item_id': {'type': 'integer', 'description': 'Cart item ID'},
                    'quantity': {'type': 'integer', 'description': 'New quantity'}
                },
                'required': ['item_id', 'quantity']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'item': {'type': 'object'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['patch'])
    def update_item(self, request):
        """
        Update cart item quantity.
        PATCH /api/v1/cart/update_item/
        Body: { "item_id": 1, "quantity": 3 }
        """
        item_id = request.data.get('item_id')

        if not item_id:
            return Response({
                'error': 'item_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart = Cart.objects.get(user=request.user)
            item = CartItem.objects.get(id=item_id, cart=cart)
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            return Response({
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = CartItemUpdateSerializer(
            item,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Cart item updated',
            'item': CartItemSerializer(item).data
        })

    @extend_schema(
        summary="Remove item from cart",
        description="""
        Remove a specific item from the shopping cart.
 
        **Query Parameters:**
        - item_id: Cart item ID to remove
 
        **Example Request:**
```
        DELETE /api/v1/cart/remove_item/?item_id=23
```
 
        **Permissions:** Authenticated users only
        """,
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Cart item ID to remove'
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'cart_items_count': {'type': 'integer'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['delete'])
    def remove_item(self, request):
        """
        Remove item from cart.
        DELETE /api/v1/cart/remove_item/?item_id=1
        """
        item_id = request.query_params.get('item_id')

        if not item_id:
            return Response({
                'error': 'item_id parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart = Cart.objects.get(user=request.user)
            item = CartItem.objects.get(id=item_id, cart=cart)
            product_name = item.product.name
            item.delete()

            return Response({
                'message': f'Removed {product_name} from cart',
                'cart_items_count': cart.items_count
            })
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            return Response({
                'error': 'Cart item not found'
            }, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(
        summary="Clear all items from cart",
        description="""
        Remove all items from the shopping cart.
 
        **Use Cases:**
        - Start fresh shopping session
        - Clear after checkout
        - Remove all items at once
 
        **Permissions:** Authenticated users only
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """
        Clear all items from cart.
        DELETE /api/v1/cart/clear/
        """
        try:
            cart = Cart.objects.get(user=request.user)
            items_count = cart.items.count()
            cart.items.all().delete()

            return Response({
                'message': f'Removed {items_count} items from cart'
            })
        except Cart.DoesNotExist:
            return Response({
                'message': 'Cart is already empty'
            })

    @extend_schema(
        summary="Checkout cart and create orders",
        description="""
        Convert cart items into orders. Creates one order per vendor.
 
        **Process:**
        1. Validates all items in stock
        2. Groups items by vendor
        3. Creates separate order for each vendor
        4. Validates minimum order values
        5. Reserves stock
        6. Clears cart items after successful orders
        7. Returns created orders
 
        **Important:**
        - Creates multiple orders if items from different vendors
        - Each order requires separate payment
        - Partial success possible (some orders created, others failed)
 
        **Example Request:**
```json
        {
            "delivery_address_id": 12,
            "delivery_notes": "Ring doorbell"
        }
```
 
        **Example Response:**
```json
        {
            "message": "Created 2 order(s)",
            "orders": [
                {
                    "order_id": 45,
                    "reference_number": "ORD-2024-001",
                    "vendor_name": "Farm Fresh",
                    "total": "45.50",
                    "items_count": 3
                }
            ],
            "failed_vendors": []
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=CheckoutSerializer,
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'orders': {'type': 'array'},
                    'failed_vendors': {'type': 'array'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['post'])
    def checkout(self, request):
        """
        Checkout cart - create orders from cart items.
        Creates one order per vendor.
        POST /api/v1/cart/checkout/
        Body: {
            "delivery_address_id": 1,
            "delivery_notes": "Optional notes"
        }
        """
        serializer = CheckoutSerializer(
            data=request.data,
            context={'request': request}
        )

        serializer.is_valid(raise_exception=True)

        delivery_address_id = serializer.validated_data['delivery_address_id']
        delivery_notes = serializer.validated_data.get('delivery_notes', '')

        try:
            cart = Cart.objects.get(user=request.user)
        except Cart.DoesNotExist:
            return Response({
                'error': 'Cart not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Group items by vendor
        items_by_vendor = cart.get_items_by_vendor()

        if not items_by_vendor:
            return Response({
                'error': 'Cart is empty'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create one order per vendor
        from apps.orders.services.order_service import OrderService
        order_service = OrderService()

        created_orders = []
        failed_vendors = []

        for vendor_id, vendor_items in items_by_vendor.items():
            # Prepare items for order creation
            order_items_data = [
                {
                    'product_id': item.product.id,
                    'quantity': item.quantity
                }
                for item in vendor_items
            ]

            # Create order
            result = order_service.create_order(
                buyer=request.user,
                vendor_id=vendor_id,
                delivery_address_id=delivery_address_id,
                items=order_items_data,
                delivery_notes=delivery_notes
            )

            if result.success:
                order = result.data
                created_orders.append({
                    'order_id': order.id,
                    'reference_number': order.reference_number,
                    'vendor_name': order.vendor.business_name,
                    'total': str(order.total),
                    'items_count': len(vendor_items)
                })

                # Remove items from cart after successful order
                for item in vendor_items:
                    item.delete()
            else:
                vendor = Vendor.objects.get(id=vendor_id)
                failed_vendors.append({
                    'vendor_name': vendor.business_name,
                    'error': result.error,
                    'error_code': result.error_code
                })

        # Return results
        if created_orders:
            return Response({
                'message': f'Created {len(created_orders)} order(s)',
                'orders': created_orders,
                'failed_vendors': failed_vendors if failed_vendors else None
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Failed to create any orders',
                'failed_vendors': failed_vendors
            }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get cart summary grouped by vendor",
        description="""
        Retrieve cart summary with items organized by vendor.
 
        **Includes per vendor:**
        - Items count
        - Subtotal, VAT, and total
        - Minimum order value
        - Whether minimum is met
        - List of items
 
        **Use Cases:**
        - Checkout preview
        - Show order separation
        - Validate minimum order values
        - Display cost breakdown
 
        **Permissions:** Authenticated users only
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'vendors': {'type': 'array'},
                    'total_vendors': {'type': 'integer'},
                    'grand_total': {'type': 'string'}
                }
            }
        },
        tags=['Cart']
    )
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get cart summary grouped by vendor.
        GET /api/v1/cart/summary/
        """
        cart = self.get_or_create_cart(request.user)
        items_by_vendor = cart.get_items_by_vendor()

        summary = []
        for vendor_id, vendor_items in items_by_vendor.items():
            vendor = vendor_items[0].product.vendor

            vendor_subtotal = sum(item.subtotal for item in vendor_items)
            vendor_vat = sum(item.vat_amount for item in vendor_items)
            vendor_total = vendor_subtotal + vendor_vat

            summary.append({
                'vendor_id': vendor.id,
                'vendor_name': vendor.business_name,
                'items_count': len(vendor_items),
                'subtotal': str(vendor_subtotal),
                'vat': str(vendor_vat),
                'total': str(vendor_total),
                'min_order_value': str(vendor.min_order_value),
                'meets_minimum': vendor_subtotal >= vendor.min_order_value,
                'items': CartItemSerializer(vendor_items, many=True).data
            })

        return Response({
            'vendors': summary,
            'total_vendors': len(summary),
            'grand_total': str(sum(
                item.total_with_vat for items in items_by_vendor.values() for item in items
            ))
        })
