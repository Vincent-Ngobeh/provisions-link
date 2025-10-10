"""
Tests for order serializers.
Tests validation, calculations, and status transitions.
"""
import pytest
from decimal import Decimal
from rest_framework.exceptions import ValidationError

from apps.orders.serializers import (
    OrderCreateSerializer,
    OrderStatusUpdateSerializer,
    OrderItemCreateSerializer
)
from apps.orders.models import Order
from tests.conftest import (
    UserFactory, VendorFactory, ProductFactory,
    OrderFactory, AddressFactory
)


@pytest.mark.django_db
class TestOrderCreateSerializer:
    """Test order creation serializer."""

    def setup_method(self):
        self.user = UserFactory()
        self.vendor = VendorFactory(
            is_approved=True,
            min_order_value=Decimal('50.00')
        )
        self.address = AddressFactory(user=self.user)
        self.product1 = ProductFactory(
            vendor=self.vendor,
            price=Decimal('25.00')
        )
        self.product2 = ProductFactory(
            vendor=self.vendor,
            price=Decimal('30.00')
        )
        self.context = {'request': type('Request', (), {'user': self.user})()}

    def test_valid_order_data(self):
        """Test serializer accepts valid order data."""
        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 2},
                {'product': self.product2.id, 'quantity': 1}
            ],
            'delivery_notes': 'Please ring doorbell'
        }

        serializer = OrderCreateSerializer(data=data, context=self.context)

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert len(validated['items']) == 2
        assert validated['delivery_notes'] == 'Please ring doorbell'

    def test_order_must_have_items(self):
        """Test that orders must contain at least one item."""
        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': []  # No items
        }

        serializer = OrderCreateSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'items' in serializer.errors
        assert 'at least one item' in str(serializer.errors['items'][0])

    def test_validates_minimum_order_value(self):
        """Test that orders must meet vendor minimum."""
        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 1}  # Only £25
            ]
        }

        serializer = OrderCreateSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'at least' in str(serializer.errors).lower()
        assert '50' in str(serializer.errors)

    def test_validates_products_belong_to_vendor(self):
        """Test that all products must belong to the specified vendor."""
        other_vendor = VendorFactory()
        other_product = ProductFactory(
            vendor=other_vendor,
            price=Decimal('50.00')
        )

        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 2},
                {'product': other_product.id, 'quantity': 1}  # Wrong vendor
            ]
        }

        serializer = OrderCreateSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert "doesn't belong to vendor" in str(serializer.errors)

    def test_calculates_order_totals(self):
        """Test that order totals are calculated correctly."""
        self.product1.vat_rate = Decimal('0.20')
        self.product1.save()
        self.product2.vat_rate = Decimal('0.20')
        self.product2.save()

        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 2},  # £50
                {'product': self.product2.id, 'quantity': 1}   # £30
            ]
        }

        serializer = OrderCreateSerializer(data=data, context=self.context)
        assert serializer.is_valid()

        # Create the order
        order = serializer.save()

        assert order.subtotal == Decimal('80.00')
        assert order.vat_amount == Decimal('16.00')  # 20% of £80
        assert order.total >= Decimal('96.00')  # Including delivery fee


@pytest.mark.django_db
class TestOrderItemCreateSerializer:
    """Test order item serializer."""

    def test_validates_positive_quantity(self):
        """Test that quantity must be positive."""
        product = ProductFactory()

        # Zero quantity
        data = {'product': product.id, 'quantity': 0}
        serializer = OrderItemCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'quantity' in serializer.errors

        # Negative quantity
        data = {'product': product.id, 'quantity': -5}
        serializer = OrderItemCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert 'quantity' in serializer.errors

        # Positive quantity - valid
        data = {'product': product.id, 'quantity': 5}
        serializer = OrderItemCreateSerializer(data=data)
        assert serializer.is_valid()


@pytest.mark.django_db
class TestOrderStatusUpdateSerializer:
    """Test order status update serializer."""

    def test_valid_status_transition(self):
        """Test valid status transitions."""
        # pending -> paid
        order = OrderFactory(status='pending')
        data = {'status': 'paid'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert serializer.is_valid()

        # paid -> processing
        order = OrderFactory(status='paid')
        data = {'status': 'processing'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert serializer.is_valid()

        # processing -> shipped
        order = OrderFactory(status='processing')
        data = {'status': 'shipped'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert serializer.is_valid()

    def test_invalid_status_transition(self):
        """Test invalid status transitions are rejected."""
        # Cannot go from pending to delivered
        order = OrderFactory(status='pending')
        data = {'status': 'delivered'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert not serializer.is_valid()
        assert 'status' in serializer.errors
        assert 'cannot transition' in str(
            serializer.errors['status'][0]).lower()

        # Cannot go back from delivered to pending
        order = OrderFactory(status='delivered')
        data = {'status': 'pending'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert not serializer.is_valid()

        # Cannot change from cancelled
        order = OrderFactory(status='cancelled')
        data = {'status': 'paid'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert not serializer.is_valid()

    def test_status_choices(self):
        """Test that only valid status choices are accepted."""
        order = OrderFactory(status='pending')
        data = {'status': 'invalid_status'}
        serializer = OrderStatusUpdateSerializer(order, data=data)
        assert not serializer.is_valid()
        assert 'status' in serializer.errors
