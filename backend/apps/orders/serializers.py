# apps/orders/serializers.py

from rest_framework import serializers
from django.db import transaction
from .models import Order, OrderItem, Cart, CartItem
from apps.core.models import Address
from apps.core.serializers import AddressSerializer
from apps.vendors.models import Vendor
from apps.vendors.serializers import VendorListSerializer
from apps.products.models import Product
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
            'status', 'items_count', 'created_at', 'group'
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Full order details"""
    buyer = serializers.SerializerMethodField()
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
            'delivered_at', 'group'
        ]

    def get_buyer(self, obj):
        """Return buyer with id for frontend comparison"""
        return {
            'id': obj.buyer.id,
            'email': obj.buyer.email,
            'username': obj.buyer.username,
            'first_name': obj.buyer.first_name,
            'last_name': obj.buyer.last_name,
        }


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


class CartItemSerializer(serializers.ModelSerializer):
    """Cart item with product details."""
    product = ProductListSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    subtotal = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    vat_amount = serializers.SerializerMethodField()

    total_with_vat = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_id', 'quantity',
            'subtotal', 'vat_amount', 'total_with_vat',
            'added_at', 'updated_at'
        ]
        read_only_fields = ['id', 'added_at', 'updated_at']

    def get_vat_amount(self, obj):
        """Get VAT amount for this item."""
        return obj.vat_amount

    def validate_product_id(self, value):
        """Validate product exists and is active."""
        try:
            product = Product.objects.get(id=value, is_active=True)
            if not product.in_stock:
                raise serializers.ValidationError("Product is out of stock")
            return value
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or inactive")

    def validate_quantity(self, value):
        """Validate quantity is positive."""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")
        return value

    def validate(self, attrs):
        """Validate quantity against stock."""
        product_id = attrs.get('product_id')
        quantity = attrs.get('quantity', 1)

        if product_id:
            try:
                product = Product.objects.get(id=product_id)
                if quantity > product.stock_quantity:
                    raise serializers.ValidationError(
                        f"Only {product.stock_quantity} units available"
                    )
            except Product.DoesNotExist:
                pass  # Already validated in validate_product_id

        return attrs


class CartSerializer(serializers.ModelSerializer):
    """Full cart with items and totals."""
    items = CartItemSerializer(many=True, read_only=True)
    items_count = serializers.IntegerField(read_only=True)
    total_value = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    subtotal = serializers.SerializerMethodField()
    vat_total = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()
    vendors_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'items', 'items_count', 'total_value',
            'subtotal', 'vat_total', 'grand_total',
            'vendors_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_subtotal(self, obj):
        """Calculate cart subtotal."""
        return sum(item.subtotal for item in obj.items.all())

    def get_vat_total(self, obj):
        """Calculate total VAT."""
        return sum(item.vat_amount for item in obj.items.all())

    def get_grand_total(self, obj):
        """Calculate grand total with VAT."""
        return sum(item.total_with_vat for item in obj.items.all())

    def get_vendors_count(self, obj):
        """Count unique vendors in cart."""
        return obj.items.select_related('product__vendor').values(
            'product__vendor'
        ).distinct().count()


class CartItemUpdateSerializer(serializers.ModelSerializer):
    """Update cart item quantity."""

    class Meta:
        model = CartItem
        fields = ['quantity']

    def validate_quantity(self, value):
        """Validate quantity against stock."""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be positive")

        # Check stock availability
        if self.instance:
            product = self.instance.product
            if value > product.stock_quantity:
                raise serializers.ValidationError(
                    f"Only {product.stock_quantity} units available"
                )

        return value


class CheckoutSerializer(serializers.Serializer):
    """Checkout validation and order creation."""
    delivery_address_id = serializers.IntegerField()
    delivery_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_delivery_address_id(self, value):
        """Validate delivery address belongs to user."""
        user = self.context['request'].user
        try:
            Address.objects.get(id=value, user=user)
            return value
        except Address.DoesNotExist:
            raise serializers.ValidationError("Address not found")

    def validate(self, attrs):
        """Validate cart is not empty."""
        user = self.context['request'].user

        try:
            cart = Cart.objects.get(user=user)
            if not cart.items.exists():
                raise serializers.ValidationError("Cart is empty")
        except Cart.DoesNotExist:
            raise serializers.ValidationError("Cart not found")

        return attrs
