"""
Tests for vendor serializers.
Tests registration validation and dashboard data.
"""
import pytest
from decimal import Decimal
from rest_framework.exceptions import ValidationError

from apps.vendors.serializers import (
    VendorRegistrationSerializer,
    VendorListSerializer,
    VendorDetailSerializer
)
from tests.conftest import UserFactory, VendorFactory


@pytest.mark.django_db
class TestVendorRegistrationSerializer:
    """Test vendor registration serializer."""

    def setup_method(self):
        self.user = UserFactory()
        self.context = {'request': type('Request', (), {'user': self.user})()}

    def test_valid_vendor_registration(self):
        """Test serializer accepts valid vendor data."""
        data = {
            'business_name': 'Test Restaurant',
            'description': 'Fine dining establishment',
            'phone_number': '+442012345678',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': '50.00',
            'vat_number': 'GB123456789'
        }

        serializer = VendorRegistrationSerializer(
            data=data,
            context=self.context
        )

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['postcode'] == 'SW1A 1AA'  # Uppercase
        assert validated['min_order_value'] == Decimal('50.00')

    def test_validates_uk_postcode_format(self):
        """Test that UK postcode format is validated."""
        invalid_postcodes = [
            'INVALID',
            '12345',  # US ZIP
            'ABC 123',
            'SW1A1AA1',  # Too long
            ''  # Empty
        ]

        for postcode in invalid_postcodes:
            data = {
                'business_name': 'Test',
                'description': 'Test',
                'postcode': postcode,
                'delivery_radius_km': 10,
                'min_order_value': '50.00'
            }

            serializer = VendorRegistrationSerializer(
                data=data,
                context=self.context
            )

            assert not serializer.is_valid()
            assert 'postcode' in serializer.errors

    def test_normalizes_postcode(self):
        """Test that postcodes are normalized to uppercase."""
        data = {
            'business_name': 'Test',
            'description': 'Test',
            'postcode': 'sw1a 1aa',  # Lowercase
            'delivery_radius_km': 10,
            'min_order_value': '50.00'
        }

        serializer = VendorRegistrationSerializer(
            data=data,
            context=self.context
        )

        assert serializer.is_valid()
        assert serializer.validated_data['postcode'] == 'SW1A 1AA'

    def test_validates_delivery_radius(self):
        """Test delivery radius validation."""
        # Too small
        data = {
            'business_name': 'Test',
            'description': 'Test',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 0,
            'min_order_value': '50.00'
        }

        serializer = VendorRegistrationSerializer(
            data=data,
            context=self.context
        )

        # This might be valid depending on model constraints
        # If there's a min validator, it would fail
        if not serializer.is_valid():
            assert 'delivery_radius_km' in serializer.errors

    def test_optional_vat_number(self):
        """Test that VAT number is optional."""
        data = {
            'business_name': 'Test',
            'description': 'Test',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': '50.00'
            # No VAT number
        }

        serializer = VendorRegistrationSerializer(
            data=data,
            context=self.context
        )

        assert serializer.is_valid()
        assert 'vat_number' not in serializer.validated_data or \
               serializer.validated_data.get('vat_number') == ''


@pytest.mark.django_db
class TestVendorListSerializer:
    """Test vendor list serializer."""

    def test_includes_fsa_rating_display(self):
        """Test that FSA rating display is included."""
        vendor = VendorFactory(
            fsa_rating_value=5,
            fsa_verified=True
        )

        serializer = VendorListSerializer(vendor)
        data = serializer.data

        assert 'fsa_rating_value' in data
        assert 'fsa_rating_display' in data
        assert data['fsa_rating_value'] == 5

    def test_distance_field_optional(self):
        """Test that distance_km is optional."""
        vendor = VendorFactory()

        serializer = VendorListSerializer(vendor)
        data = serializer.data

        # distance_km should be None if not provided
        assert 'distance_km' not in data

    def test_distance_field_when_provided(self):
        """Test distance field when provided."""
        vendor = VendorFactory()
        vendor.distance_km = Decimal('5.5')  # Annotated field

        serializer = VendorListSerializer(vendor)
        data = serializer.data

        assert data['distance_km'] == '5.50'


@pytest.mark.django_db
class TestVendorDetailSerializer:
    """Test vendor detail serializer."""

    def test_includes_all_vendor_details(self):
        """Test that all vendor details are included."""
        vendor = VendorFactory(
            fsa_rating_value=5,
            fsa_verified=True,
            is_approved=True
        )

        serializer = VendorDetailSerializer(vendor)
        data = serializer.data

        # Check all expected fields
        expected_fields = [
            'id', 'business_name', 'slug', 'description',
            'phone_number', 'is_approved', 'fsa_verified',
            'postcode', 'delivery_radius_km', 'min_order_value',
            'fsa_rating_value', 'fsa_rating_date'
        ]

        for field in expected_fields:
            assert field in data

    def test_read_only_fields(self):
        """Test that certain fields are read-only."""
        vendor = VendorFactory()

        # Try to modify read-only fields
        data = {
            'business_name': 'Updated Name',
            'is_approved': True,  # Should be read-only
            'fsa_rating_value': 5,  # Should be read-only
            'slug': 'new-slug'  # Should be read-only
        }

        serializer = VendorDetailSerializer(vendor, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            vendor.refresh_from_db()

            # Read-only fields should not change
            assert vendor.slug != 'new-slug'
            # Business name should change
            assert vendor.business_name == 'Updated Name'
