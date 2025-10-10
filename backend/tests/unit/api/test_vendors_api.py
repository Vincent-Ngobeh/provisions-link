"""
API tests for vendor endpoints.
Tests registration, approval, and dashboard access.
"""
import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse

from apps.vendors.models import Vendor
from tests.conftest import UserFactory, VendorFactory


@pytest.mark.django_db
class TestVendorRegistrationAPI:
    """Test vendor registration endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('vendor-register')
        self.user = UserFactory()

    def test_authenticated_user_can_register_vendor(self):
        """Test that authenticated users can register as vendors."""
        self.client.force_authenticate(self.user)

        data = {
            'business_name': 'Test Restaurant',
            'description': 'Fine dining establishment',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': '50.00',
            'phone_number': '+442012345678',
            'vat_number': 'GB123456789'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['vendor']['business_name'] == 'Test Restaurant'
        assert 'onboarding_url' in response.data

        # Verify vendor was created
        vendor = Vendor.objects.get(user=self.user)
        assert vendor.business_name == 'Test Restaurant'
        assert vendor.is_approved is False  # Requires admin approval

    def test_unauthenticated_cannot_register_vendor(self):
        """Test that unauthenticated users cannot register as vendors."""
        data = {
            'business_name': 'Test Restaurant',
            'description': 'Test',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': '50.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_cannot_register_multiple_vendors(self):
        """Test that users can only have one vendor account."""
        self.client.force_authenticate(self.user)

        # Create first vendor
        VendorFactory(user=self.user)

        # Try to create second
        data = {
            'business_name': 'Another Business',
            'description': 'Test',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': '50.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already' in str(response.data).lower()

    def test_vendor_registration_validates_postcode(self):
        """Test that invalid postcodes are rejected."""
        self.client.force_authenticate(self.user)

        data = {
            'business_name': 'Test Restaurant',
            'description': 'Test',
            'postcode': 'INVALID',
            'delivery_radius_km': 10,
            'min_order_value': '50.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'postcode' in str(response.data).lower()


@pytest.mark.django_db
class TestVendorApprovalAPI:
    """Test vendor approval endpoint (admin only)."""

    def setup_method(self):
        self.client = APIClient()
        self.vendor = VendorFactory(is_approved=False, fsa_rating_value=4)
        self.url = reverse('vendor-approve', kwargs={'pk': self.vendor.id})

        self.admin = UserFactory(is_staff=True)
        self.regular_user = UserFactory()

    def test_admin_can_approve_vendor(self):
        """Test that admins can approve vendors."""
        self.client.force_authenticate(self.admin)

        data = {'commission_rate': '0.12'}

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK

        self.vendor.refresh_from_db()
        assert self.vendor.is_approved is True
        assert self.vendor.commission_rate == Decimal('0.12')

    def test_non_admin_cannot_approve_vendor(self):
        """Test that regular users cannot approve vendors."""
        self.client.force_authenticate(self.regular_user)

        data = {'commission_rate': '0.12'}

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approval_validates_commission_rate(self):
        """Test that commission rate must be reasonable."""
        self.client.force_authenticate(self.admin)

        data = {'commission_rate': '0.99'}  # 99% - too high

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'commission' in str(response.data).lower()


@pytest.mark.django_db
class TestVendorDashboardAPI:
    """Test vendor dashboard access."""

    def setup_method(self):
        self.client = APIClient()
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user)
        self.url = reverse('vendor-dashboard', kwargs={'pk': self.vendor.id})

        self.other_user = UserFactory()
        self.staff_user = UserFactory(is_staff=True)

    def test_vendor_can_access_own_dashboard(self):
        """Test that vendors can access their own dashboard."""
        self.client.force_authenticate(self.vendor_user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert 'summary' in response.data
        assert 'today_revenue' in response.data['summary']
        assert 'pending_orders' in response.data['summary']

    def test_other_user_cannot_access_vendor_dashboard(self):
        """Test that other users cannot access vendor dashboard."""
        self.client.force_authenticate(self.other_user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_staff_can_access_any_vendor_dashboard(self):
        """Test that staff can access any vendor's dashboard."""
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
