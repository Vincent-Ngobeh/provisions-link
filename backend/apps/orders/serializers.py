# apps/orders/serializers.py

from rest_framework import serializers
from django.db import transaction
from .models import Order, OrderItem
from apps.core.serializers import AddressSerializer
from apps.vendors.serializers import VendorListSerializer
from apps.products.serializers import ProductListSerializer


class OrderItemSerializer(serializers.ModelSerializer):
    """Order item details"""
    product = ProductListSerializer(read_only=True)
    vat_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'quantity', 'unit_price',
            'total_price', 'discount_amount', 'vat_amount'
        ]
        read_only_fields = ['id', 'unit_price', 'total_price', 'vat_amount']


class OrderItemCreateSerializer(serializers.ModelSerializer):
    """Create order items"""

    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight order for listings"""
    vendor_name = serializers.CharField(
        source='vendor.business_name', read_only=True
    )
    items_count = serializers.IntegerField(
        source='items.count', read_only=True
    )

    class Meta:
        model = Order
        fields = [
            'id', 'reference_number', 'vendor_name', 'total',
            'status', 'items_count', 'created_at'
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Full order details"""
    buyer = serializers.StringRelatedField(read_only=True)
    vendor = VendorListSerializer(read_only=True)
    delivery_address = AddressSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'reference_number', 'buyer', 'vendor',
            'delivery_address', 'items', 'subtotal', 'vat_amount',
            'delivery_fee', 'total', 'marketplace_fee', 'vendor_payout',
            'status', 'delivery_notes', 'created_at', 'paid_at',
            'delivered_at'
        ]


class OrderCreateSerializer(serializers.ModelSerializer):
    """Create order with items"""
    items = OrderItemCreateSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            'vendor', 'delivery_address', 'items',
            'delivery_notes', 'group'
        ]

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "Order must contain at least one item"
            )
        return value

    def validate(self, attrs):
        # Verify all items belong to the same vendor
        vendor = attrs['vendor']
        for item_data in attrs['items']:
            if item_data['product'].vendor != vendor:
                raise serializers.ValidationError(
                    f"Product {item_data['product'].name} doesn't belong to vendor {vendor.business_name}"
                )

        # Check minimum order value
        total = sum(
            item['product'].price * item['quantity']
            for item in attrs['items']
        )
        if total < vendor.min_order_value:
            raise serializers.ValidationError(
                f"Order total must be at least £{vendor.min_order_value}"
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        validated_data['buyer'] = self.context['request'].user

        # Calculate totals (will be done in service layer)
        subtotal = sum(
            item['product'].price * item['quantity']
            for item in items_data
        )
        vat_amount = sum(
            item['product'].price * item['quantity'] * item['product'].vat_rate
            for item in items_data
        )
        validated_data['subtotal'] = subtotal
        validated_data['vat_amount'] = vat_amount
        validated_data['total'] = subtotal + vat_amount + \
            validated_data.get('delivery_fee', 0)

        order = Order.objects.create(**validated_data)

        # Create order items
        for item_data in items_data:
            OrderItem.objects.create(
                order=order,
                product=item_data['product'],
                quantity=item_data['quantity'],
                unit_price=item_data['product'].price,
                total_price=item_data['product'].price * item_data['quantity']
            )

        return order


class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    """Update order status (vendor/admin only)"""

    class Meta:
        model = Order
        fields = ['status']

    def validate_status(self, value):
        # Define valid status transitions
        current_status = self.instance.status
        valid_transitions = {
            'pending': ['paid', 'cancelled'],
            'paid': ['processing', 'cancelled', 'refunded'],
            'processing': ['shipped', 'cancelled', 'refunded'],
            'shipped': ['delivered', 'refunded'],
            'delivered': ['refunded'],
            'cancelled': [],
            'refunded': []
        }

        if value not in valid_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Cannot transition from {current_status} to {value}"
            )

        return value
