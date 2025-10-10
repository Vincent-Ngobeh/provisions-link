"""
API tests for buying group endpoints.
Tests group creation, commitments, and real-time status.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.buying_groups.models import BuyingGroup, GroupCommitment
from tests.conftest import (
    UserFactory, VendorFactory, ProductFactory,
    BuyingGroupFactory, GroupCommitmentFactory
)


@pytest.mark.django_db
class TestBuyingGroupCreateAPI:
    """Test buying group creation endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('buyinggroup-create-group')
        self.user = UserFactory()
        self.vendor = VendorFactory(is_approved=True)
        self.product = ProductFactory(
            vendor=self.vendor,
            price=Decimal('50.00'),
            stock_quantity=200
        )

    def test_authenticated_user_can_create_group(self):
        """Test that authenticated users can create buying groups."""
        self.client.force_authenticate(self.user)

        data = {
            'product_id': self.product.id,
            'postcode': 'SW1A 1AA',
            'target_quantity': 50,
            'discount_percent': '15.00',
            'duration_days': 7,
            'radius_km': 5
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['product']['id'] == self.product.id
        assert Decimal(response.data['discount_percent']) == Decimal('15.00')

        # Verify group was created
        group = BuyingGroup.objects.get(id=response.data['id'])
        assert group.status == 'open'
        assert group.target_quantity == 50

    def test_unauthenticated_cannot_create_group(self):
        """Test that unauthenticated users cannot create groups."""
        data = {
            'product_id': self.product.id,
            'postcode': 'SW1A 1AA'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_group_requires_product_and_postcode(self):
        """Test that product_id and postcode are required."""
        self.client.force_authenticate(self.user)

        # Missing product_id
        data = {'postcode': 'SW1A 1AA'}
        response = self.client.post(self.url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'product_id' in str(response.data).lower()

        # Missing postcode
        data = {'product_id': self.product.id}
        response = self.client.post(self.url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'postcode' in str(response.data).lower()

    def test_create_group_validates_product_stock(self):
        """Test that groups cannot be created for low stock products."""
        low_stock_product = ProductFactory(
            vendor=self.vendor,
            stock_quantity=5  # Very low stock
        )
        self.client.force_authenticate(self.user)

        data = {
            'product_id': low_stock_product.id,
            'postcode': 'SW1A 1AA',
            'target_quantity': 50
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'stock' in str(response.data).lower()


@pytest.mark.django_db
class TestBuyingGroupCommitAPI:
    """Test commitment to buying groups."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.vendor = VendorFactory(is_approved=True)
        self.product = ProductFactory(
            vendor=self.vendor, price=Decimal('25.00'))
        self.group = BuyingGroupFactory(
            product=self.product,
            status='open',
            target_quantity=100,
            current_quantity=20,
            discount_percent=Decimal('15.00')
        )
        self.url = reverse('buyinggroup-commit', kwargs={'pk': self.group.id})

    def test_authenticated_user_can_commit(self):
        """Test that authenticated users can commit to groups."""
        self.client.force_authenticate(self.user)

        data = {
            'quantity': 5,
            'postcode': 'SW1A 1AA'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert 'commitment' in response.data
        assert 'payment_intent' in response.data
        assert response.data['group_progress'] == 25.0  # (20+5)/100

        # Verify commitment was created
        commitment = GroupCommitment.objects.get(
            group=self.group,
            buyer=self.user
        )
        assert commitment.quantity == 5
        assert commitment.status == 'pending'

    def test_unauthenticated_cannot_commit(self):
        """Test that unauthenticated users cannot commit."""
        data = {
            'quantity': 5,
            'postcode': 'SW1A 1AA'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_cannot_commit_twice(self):
        """Test that users cannot commit to the same group twice."""
        self.client.force_authenticate(self.user)

        # First commitment
        GroupCommitmentFactory(
            group=self.group,
            buyer=self.user,
            quantity=5,
            status='pending'
        )

        # Try second commitment
        data = {
            'quantity': 3,
            'postcode': 'SW1A 1AA'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already' in str(response.data).lower()

    def test_cannot_commit_to_expired_group(self):
        """Test that users cannot commit to expired groups."""
        self.client.force_authenticate(self.user)

        # Expire the group
        self.group.expires_at = timezone.now() - timedelta(hours=1)
        self.group.save()

        data = {
            'quantity': 5,
            'postcode': 'SW1A 1AA'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'expired' in str(response.data).lower()

    def test_commit_validates_required_fields(self):
        """Test that quantity and postcode are required."""
        self.client.force_authenticate(self.user)

        # Missing quantity
        data = {'postcode': 'SW1A 1AA'}
        response = self.client.post(self.url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Missing postcode
        data = {'quantity': 5}
        response = self.client.post(self.url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestBuyingGroupCancelCommitmentAPI:
    """Test cancelling commitments."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.group = BuyingGroupFactory(status='open')
        self.commitment = GroupCommitmentFactory(
            group=self.group,
            buyer=self.user,
            quantity=5,
            status='pending'
        )
        self.url = reverse('buyinggroup-cancel-commitment',
                           kwargs={'pk': self.group.id})

    def test_user_can_cancel_own_commitment(self):
        """Test that users can cancel their own commitments."""
        self.client.force_authenticate(self.user)

        response = self.client.post(self.url)

        assert response.status_code == status.HTTP_200_OK

        self.commitment.refresh_from_db()
        assert self.commitment.status == 'cancelled'

    def test_user_cannot_cancel_others_commitment(self):
        """Test that users cannot cancel other users' commitments."""
        other_user = UserFactory()
        self.client.force_authenticate(other_user)

        response = self.client.post(self.url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert 'no active commitment' in str(response.data).lower()

    def test_cannot_cancel_after_group_completed(self):
        """Test that commitments cannot be cancelled after group completes."""
        self.group.status = 'completed'
        self.group.save()

        self.client.force_authenticate(self.user)

        response = self.client.post(self.url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestBuyingGroupListAPI:
    """Test buying group listing and filtering."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('buyinggroup-list')

        # Create groups with different statuses
        self.open_group = BuyingGroupFactory(
            status='open',
            expires_at=timezone.now() + timedelta(days=3)
        )
        self.expired_group = BuyingGroupFactory(
            status='open',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        self.completed_group = BuyingGroupFactory(status='completed')

    def test_list_groups_no_auth_required(self):
        """Test that listing groups doesn't require authentication."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data

    def test_filter_groups_by_status(self):
        """Test filtering groups by status."""
        response = self.client.get(self.url, {'status': 'open'})

        assert response.status_code == status.HTTP_200_OK
        for group in response.data['results']:
            assert group['status'] == 'open'

    def test_hide_expired_groups_by_default(self):
        """Test that expired groups are hidden by default."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        group_ids = [g['id'] for g in response.data['results']]
        assert self.expired_group.id not in group_ids

    def test_show_expired_groups_when_requested(self):
        """Test showing expired groups when explicitly requested."""
        response = self.client.get(self.url, {'hide_expired': 'false'})

        assert response.status_code == status.HTTP_200_OK
        group_ids = [g['id'] for g in response.data['results']]
        assert self.expired_group.id in group_ids


@pytest.mark.django_db
class TestBuyingGroupNearMeAPI:
    """Test location-based group search."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('buyinggroup-near-me')

        from django.contrib.gis.geos import Point
        # Create groups at different locations
        self.nearby_group = BuyingGroupFactory(
            center_point=Point(-0.1276, 51.5074),
            radius_km=5,
            status='open'
        )
        self.far_group = BuyingGroupFactory(
            center_point=Point(-1.0000, 52.0000),
            radius_km=5,
            status='open'
        )

    def test_find_groups_near_location(self):
        """Test finding groups near a postcode."""
        with patch('apps.integrations.services.geocoding_service.GeocodingService.geocode_postcode') as mock_geocode:
            from django.contrib.gis.geos import Point
            mock_geocode.return_value.success = True
            mock_geocode.return_value.data = {
                'point': Point(-0.1276, 51.5074)
            }

            response = self.client.get(self.url, {
                'postcode': 'SW1A 1AA',
                'radius': 10
            })

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] >= 1
        assert response.data['location'] == 'SW1A 1AA'

    def test_near_me_requires_postcode(self):
        """Test that postcode is required for near_me."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'postcode' in str(response.data).lower()


@pytest.mark.django_db
class TestBuyingGroupRealtimeStatusAPI:
    """Test real-time status endpoint for WebSocket init."""

    def setup_method(self):
        self.client = APIClient()
        self.group = BuyingGroupFactory(
            status='open',
            target_quantity=100,
            current_quantity=45
        )
        self.url = reverse('buyinggroup-realtime-status',
                           kwargs={'pk': self.group.id})

    def test_get_realtime_status(self):
        """Test getting real-time group status."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert 'group' in response.data
        assert 'recent_updates' in response.data

        group_data = response.data['group']
        assert group_data['id'] == self.group.id
        assert group_data['current_quantity'] == 45
        assert group_data['progress_percent'] == 45.0
