"""
API tests for order endpoints.
Tests order creation, status updates, and permissions.
"""
import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse

from apps.orders.models import Order
from tests.conftest import (
    UserFactory, VendorFactory, ProductFactory,
    OrderFactory, AddressFactory
)


@pytest.mark.django_db
class TestOrderCreateAPI:
    """Test order creation endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('order-list')
        self.buyer = UserFactory()
        self.vendor = VendorFactory(
            is_approved=True,
            min_order_value=Decimal('50.00')
        )
        self.address = AddressFactory(user=self.buyer)
        self.product1 = ProductFactory(
            vendor=self.vendor,
            price=Decimal('25.00'),
            stock_quantity=100
        )
        self.product2 = ProductFactory(
            vendor=self.vendor,
            price=Decimal('30.00'),
            stock_quantity=50
        )

    def test_authenticated_user_can_create_order(self):
        """Test that authenticated users can create orders."""
        self.client.force_authenticate(self.buyer)

        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 2},
                {'product': self.product2.id, 'quantity': 1}
            ],
            'delivery_notes': 'Ring doorbell twice'
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_201_CREATED

        # Verify order calculations
        order = Order.objects.get(id=response.data['id'])
        assert order.subtotal == Decimal('80.00')  # (25*2) + (30*1)
        assert order.buyer == self.buyer
        assert order.vendor == self.vendor

    def test_unauthenticated_cannot_create_order(self):
        """Test that unauthenticated users cannot create orders."""
        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 1}
            ]
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_order_validates_minimum_value(self):
        """Test that orders must meet vendor minimum."""
        self.client.force_authenticate(self.buyer)

        # Order below minimum (1 * 25 = 25, min is 50)
        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 1}
            ]
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'at least' in str(response.data).lower()

    def test_order_validates_stock_availability(self):
        """Test that orders check stock availability."""
        self.client.force_authenticate(self.buyer)

        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                # More than available
                {'product': self.product1.id, 'quantity': 200}
            ]
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'stock' in str(response.data).lower()

    def test_order_validates_products_same_vendor(self):
        """Test that all products must be from same vendor."""
        other_vendor = VendorFactory()
        other_product = ProductFactory(vendor=other_vendor)

        self.client.force_authenticate(self.buyer)

        data = {
            'vendor': self.vendor.id,
            'delivery_address': self.address.id,
            'items': [
                {'product': self.product1.id, 'quantity': 2},
                {'product': other_product.id, 'quantity': 1}  # Different vendor
            ]
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestOrderStatusUpdateAPI:
    """Test order status update endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.buyer = UserFactory()
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user)
        self.order = OrderFactory(
            buyer=self.buyer,
            vendor=self.vendor,
            status='pending'
        )
        self.url = reverse('order-update-status', kwargs={'pk': self.order.id})

    def test_vendor_can_update_order_status(self):
        """Test that vendors can update their order status."""
        self.client.force_authenticate(self.vendor_user)

        data = {'status': 'processing'}

        # First mark as paid (required transition)
        self.order.status = 'paid'
        self.order.save()

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        self.order.refresh_from_db()
        assert self.order.status == 'processing'

    def test_buyer_cannot_update_order_status(self):
        """Test that buyers cannot update order status."""
        self.client.force_authenticate(self.buyer)

        data = {'status': 'processing'}

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_invalid_status_transition_rejected(self):
        """Test that invalid status transitions are rejected."""
        self.client.force_authenticate(self.vendor_user)

        # Try to go from pending directly to delivered (invalid)
        data = {'status': 'delivered'}

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'cannot transition' in str(response.data).lower()


@pytest.mark.django_db
class TestOrderListFilteringAPI:
    """Test order list filtering and permissions."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('order-list')

        # Create users
        self.buyer1 = UserFactory()
        self.buyer2 = UserFactory()
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user)
        self.staff_user = UserFactory(is_staff=True)

        # Create orders
        self.buyer1_order = OrderFactory(buyer=self.buyer1, vendor=self.vendor)
        self.buyer2_order = OrderFactory(buyer=self.buyer2, vendor=self.vendor)
        self.other_vendor_order = OrderFactory(buyer=self.buyer1)

    def test_buyer_sees_only_own_orders(self):
        """Test that buyers only see their own orders."""
        self.client.force_authenticate(self.buyer1)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        order_ids = [o['id'] for o in response.data['results']]
        assert self.buyer1_order.id in order_ids
        assert self.buyer2_order.id not in order_ids

    def test_vendor_sees_only_their_orders(self):
        """Test that vendors only see orders for their products."""
        self.client.force_authenticate(self.vendor_user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        order_ids = [o['id'] for o in response.data['results']]
        assert self.buyer1_order.id in order_ids
        assert self.buyer2_order.id in order_ids
        assert self.other_vendor_order.id not in order_ids

    def test_staff_sees_all_orders(self):
        """Test that staff can see all orders."""
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
