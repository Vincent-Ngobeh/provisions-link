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

    def list(self, request):
        """
        Get user's cart with all items.
        GET /api/v1/cart/
        """
        cart = self.get_or_create_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

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
        logger = logging.getLogger(__name__)

        logger.error(f"=== CHECKOUT DEBUG START ===")
        logger.error(f"Request data: {request.data}")
        logger.error(
            f"User: {request.user.id if request.user.is_authenticated else 'Anonymous'}")

        serializer = CheckoutSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            logger.error(f"Validation errors: {serializer.errors}")

        serializer.is_valid(raise_exception=True)

        delivery_address_id = serializer.validated_data['delivery_address_id']
        delivery_notes = serializer.validated_data.get('delivery_notes', '')

        try:
            cart = Cart.objects.get(user=request.user)
            logger.error(
                f"Cart found: ID={cart.id}, Items count={cart.items.count()}")
        except Cart.DoesNotExist:
            logger.error("Cart not found for user")
            return Response({
                'error': 'Cart not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Group items by vendor
        items_by_vendor = cart.get_items_by_vendor()
        logger.error(
            f"Items grouped by vendor: {len(items_by_vendor)} vendors")

        if not items_by_vendor:
            logger.error("Cart is empty - no items by vendor")
            return Response({
                'error': 'Cart is empty'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create one order per vendor
        from apps.orders.services.order_service import OrderService
        order_service = OrderService()

        created_orders = []
        failed_vendors = []

        for vendor_id, vendor_items in items_by_vendor.items():
            logger.error(
                f"Processing vendor {vendor_id}: {len(vendor_items)} items")

            # Prepare items for order creation
            order_items_data = [
                {
                    'product_id': item.product.id,
                    'quantity': item.quantity
                }
                for item in vendor_items
            ]

            logger.error(f"Order items data: {order_items_data}")

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
                logger.error(f"Order created successfully: {order.id}")
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
                logger.error(
                    f"Order creation failed for vendor {vendor_id}: {result.error} ({result.error_code})")
                vendor = Vendor.objects.get(id=vendor_id)
                failed_vendors.append({
                    'vendor_name': vendor.business_name,
                    'error': result.error,
                    'error_code': result.error_code
                })

        logger.error(f"=== CHECKOUT DEBUG END ===")
        logger.error(
            f"Created orders: {len(created_orders)}, Failed: {len(failed_vendors)}")

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
