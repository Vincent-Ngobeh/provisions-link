"""
ViewSet implementations for order operations.
Handles order creation, processing, and fulfillment.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum, Count
from django.utils import timezone
from datetime import datetime, timedelta

from .models import Order, OrderItem
from .serializers import (
    OrderListSerializer,
    OrderDetailSerializer,
    OrderCreateSerializer,
    OrderStatusUpdateSerializer
)
from .services.order_service import OrderService


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

    def perform_create(self, serializer):
        """Create order using service layer."""
        items = serializer.validated_data.pop('items', [])

        # Prepare items data for service
        items_data = [
            {
                'product_id': item['product'].id,
                'quantity': item['quantity']
            }
            for item in items
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
            return Response({
                'error': result.error,
                'error_code': result.error_code
            }, status=status.HTTP_400_BAD_REQUEST)

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

        result = self.service.update_order_status(
            order_id=order.id,
            new_status=new_status,
            user=request.user,
            notes=notes
        )

        if result.success:
            return Response({
                'message': f'Order status updated to {new_status}',
                'order': OrderDetailSerializer(order.refresh_from_db()).data
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
