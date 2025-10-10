"""
Tests for buying group serializers.
Tests group creation validation, commitment rules, and real-time data.
"""
import pytest
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.buying_groups.serializers import (
    BuyingGroupCreateSerializer,
    GroupCommitmentSerializer,
    BuyingGroupRealtimeSerializer,
    BuyingGroupListSerializer
)
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from tests.conftest import (
    UserFactory, ProductFactory, BuyingGroupFactory,
    GroupCommitmentFactory, VendorFactory
)


@pytest.mark.django_db
class TestBuyingGroupCreateSerializer:
    """Test buying group creation serializer."""

    def setup_method(self):
        from django.contrib.gis.geos import Point
        self.vendor = VendorFactory(is_approved=True)
        self.product = ProductFactory(
            vendor=self.vendor, price=Decimal('50.00'))

    def test_valid_group_creation_data(self):
        """Test serializer accepts valid group data."""
        from django.contrib.gis.geos import Point

        data = {
            'product': self.product.id,
            'center_point': {'type': 'Point', 'coordinates': [-0.1276, 51.5074]},
            'radius_km': 5,
            'area_name': 'Westminster',
            'target_quantity': 50,
            'min_quantity': 30,
            'discount_percent': '15.00',
            'expires_at': (timezone.now() + timedelta(days=7)).isoformat()
        }

        serializer = BuyingGroupCreateSerializer(data=data)

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['target_quantity'] == 50
        assert validated['discount_percent'] == Decimal('15.00')

    def test_expires_at_must_be_future(self):
        """Test that expiry date must be in the future."""
        from django.contrib.gis.geos import Point

        data = {
            'product': self.product.id,
            'center_point': Point(-0.1276, 51.5074),
            'radius_km': 5,
            'area_name': 'Test Area',
            'target_quantity': 50,
            'min_quantity': 30,
            'discount_percent': '15.00',
            # Past
            'expires_at': (timezone.now() - timedelta(hours=1)).isoformat()
        }

        serializer = BuyingGroupCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert 'expires_at' in serializer.errors
        assert 'future' in str(serializer.errors['expires_at'][0])

    def test_expires_at_max_duration(self):
        """Test that groups cannot run for more than 30 days."""
        from django.contrib.gis.geos import Point

        data = {
            'product': self.product.id,
            'center_point': Point(-0.1276, 51.5074),
            'radius_km': 5,
            'area_name': 'Test Area',
            'target_quantity': 50,
            'min_quantity': 30,
            'discount_percent': '15.00',
            # Too far
            'expires_at': (timezone.now() + timedelta(days=35)).isoformat()
        }

        serializer = BuyingGroupCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert 'expires_at' in serializer.errors
        assert '30 days' in str(serializer.errors['expires_at'][0])

    def test_min_quantity_cannot_exceed_target(self):
        """Test that minimum quantity cannot exceed target."""
        from django.contrib.gis.geos import Point

        data = {
            'product': self.product.id,
            'center_point': Point(-0.1276, 51.5074),
            'radius_km': 5,
            'area_name': 'Test Area',
            'target_quantity': 50,
            'min_quantity': 60,  # Higher than target
            'discount_percent': '15.00',
            'expires_at': (timezone.now() + timedelta(days=7)).isoformat()
        }

        serializer = BuyingGroupCreateSerializer(data=data)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'cannot exceed target' in str(serializer.errors)


@pytest.mark.django_db
class TestGroupCommitmentSerializer:
    """Test group commitment serializer."""

    def setup_method(self):
        self.user = UserFactory()
        self.group = BuyingGroupFactory(
            status='open',
            target_quantity=100,
            current_quantity=20,
            discount_percent=Decimal('15.00'),
            expires_at=timezone.now() + timedelta(days=3)
        )
        self.context = {'request': type('Request', (), {'user': self.user})()}

    def test_valid_commitment_data(self):
        """Test serializer accepts valid commitment data."""
        data = {
            'group': self.group.id,
            'quantity': 5,
            'buyer_postcode': 'SW1A 1AA'
        }

        serializer = GroupCommitmentSerializer(data=data, context=self.context)

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['quantity'] == 5
        assert validated['buyer_postcode'] == 'SW1A 1AA'

    def test_cannot_commit_to_closed_group(self):
        """Test that commitments to closed groups are rejected."""
        self.group.status = 'completed'
        self.group.save()

        data = {
            'group': self.group.id,
            'quantity': 5,
            'buyer_postcode': 'SW1A 1AA'
        }

        serializer = GroupCommitmentSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'no longer accepting' in str(serializer.errors).lower()

    def test_cannot_commit_to_expired_group(self):
        """Test that commitments to expired groups are rejected."""
        self.group.expires_at = timezone.now() - timedelta(hours=1)
        self.group.save()

        data = {
            'group': self.group.id,
            'quantity': 5,
            'buyer_postcode': 'SW1A 1AA'
        }

        serializer = GroupCommitmentSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'expired' in str(serializer.errors).lower()

    def test_prevents_duplicate_commitment(self):
        """Test that users cannot commit twice to same group."""
        # Create existing commitment
        GroupCommitmentFactory(
            group=self.group,
            buyer=self.user,
            status='pending'
        )

        data = {
            'group': self.group.id,
            'quantity': 5,
            'buyer_postcode': 'SW1A 1AA'
        }

        serializer = GroupCommitmentSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'already committed' in str(serializer.errors).lower()

    def test_includes_calculated_fields(self):
        """Test that calculated fields are included in output."""
        commitment = GroupCommitmentFactory(
            group=self.group,
            buyer=self.user,
            quantity=10
        )

        serializer = GroupCommitmentSerializer(commitment)
        data = serializer.data

        assert 'total_price' in data
        assert 'total_savings' in data
        # Price should be (product_price * quantity * (1 - discount))
        # Assuming product price is available through the group


@pytest.mark.django_db
class TestBuyingGroupRealtimeSerializer:
    """Test real-time WebSocket serializer."""

    def test_includes_realtime_fields(self):
        """Test that real-time fields are included."""
        group = BuyingGroupFactory(
            target_quantity=100,
            current_quantity=45,
            expires_at=timezone.now() + timedelta(hours=12),
            status='open'
        )

        # Add some commitments
        GroupCommitmentFactory.create_batch(3, group=group)

        serializer = BuyingGroupRealtimeSerializer(group)
        data = serializer.data

        assert 'progress_percent' in data
        assert 'time_remaining' in data
        assert 'current_participants' in data
        assert data['progress_percent'] == 45.0
        assert data['current_participants'] >= 3

    def test_time_remaining_calculation(self):
        """Test that time remaining is calculated correctly."""
        # Group expiring in 2 hours
        group = BuyingGroupFactory(
            expires_at=timezone.now() + timedelta(hours=2)
        )

        serializer = BuyingGroupRealtimeSerializer(group)
        data = serializer.data

        time_remaining = data['time_remaining']
        # Should be approximately 7200 seconds (2 hours)
        assert 7100 <= time_remaining <= 7300

    def test_expired_group_time_remaining(self):
        """Test that expired groups show 0 time remaining."""
        group = BuyingGroupFactory(
            expires_at=timezone.now() - timedelta(hours=1)  # Expired
        )

        serializer = BuyingGroupRealtimeSerializer(group)
        data = serializer.data

        assert data['time_remaining'] == 0


@pytest.mark.django_db
class TestBuyingGroupListSerializer:
    """Test buying group list serializer."""

    def test_includes_vendor_and_product_names(self):
        """Test that vendor and product names are included."""
        vendor = VendorFactory(business_name='Test Vendor')
        product = ProductFactory(vendor=vendor, name='Test Product')
        group = BuyingGroupFactory(
            product=product,
            area_name='Westminster',
            target_quantity=100,
            current_quantity=45
        )

        serializer = BuyingGroupListSerializer(group)
        data = serializer.data

        assert data['product_name'] == 'Test Product'
        assert data['vendor_name'] == 'Test Vendor'
        assert data['area_name'] == 'Westminster'

    def test_time_remaining_format(self):
        """Test that time remaining is formatted as human-readable."""
        # Group expiring in 3 hours 30 minutes
        group = BuyingGroupFactory(
            expires_at=timezone.now() + timedelta(hours=3, minutes=30)
        )

        serializer = BuyingGroupListSerializer(group)
        data = serializer.data

        assert '3h 30m' in data['time_remaining'] or '3h 29m' in data['time_remaining']

    def test_expired_group_shows_expired(self):
        """Test that expired groups show 'Expired' status."""
        group = BuyingGroupFactory(
            expires_at=timezone.now() - timedelta(hours=1)
        )

        serializer = BuyingGroupListSerializer(group)
        data = serializer.data

        assert data['time_remaining'] == 'Expired'

    def test_progress_percent_calculation(self):
        """Test that progress percentage is calculated correctly."""
        group = BuyingGroupFactory(
            target_quantity=200,
            current_quantity=50
        )

        serializer = BuyingGroupListSerializer(group)
        data = serializer.data

        assert data['progress_percent'] == 25.0
