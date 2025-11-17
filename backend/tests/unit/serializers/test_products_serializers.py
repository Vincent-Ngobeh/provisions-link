"""
Tests for product serializers.
Tests validation, field requirements, and data transformation.
"""
import pytest
from decimal import Decimal
from rest_framework.exceptions import ValidationError

from apps.products.serializers import (
    ProductCreateUpdateSerializer,
    ProductSearchSerializer,
    ProductListSerializer
)
from apps.products.models import Product
from tests.conftest import ProductFactory, VendorFactory, UserFactory, CategoryFactory, TagFactory


@pytest.mark.django_db
class TestProductCreateUpdateSerializer:
    """Test product creation/update serializer validation."""

    def setup_method(self):
        self.user = UserFactory()
        self.vendor = VendorFactory(user=self.user)
        self.category = CategoryFactory()

    def test_valid_product_data(self):
        """Test serializer accepts valid product data."""
        data = {
            'name': 'Test Product',
            'description': 'Test description',
            'category': self.category.id,
            'sku': 'TEST-001',
            'price': '10.99',
            'unit': 'kg',
            'stock_quantity': 100,
            'vat_rate': '0.20'
        }

        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={'request': type('Request', (), {'user': self.user})()}
        )

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['price'] == Decimal('10.99')
        assert validated['vat_rate'] == Decimal('0.20')

    def test_allergen_info_validation(self):
        """Test that allergen info includes all required fields."""
        data = {
            'name': 'Test Product',
            'description': 'Test description',
            'sku': 'TEST-SKU-001',
            'category': self.category.id,
            'price': '10.00',
            'unit': 'unit',
            'contains_allergens': True,
            'allergen_info': {'milk': True, 'eggs': False}  # Incomplete
        }

        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={'request': type('Request', (), {'user': self.user})()}
        )

        assert serializer.is_valid()
        allergen_info = serializer.validated_data['allergen_info']

        # Should have all 14 allergen fields
        assert len(allergen_info) == 14
        assert allergen_info['milk'] is True
        assert allergen_info['eggs'] is False
        assert allergen_info['cereals_containing_gluten'] is False  # Default

    def test_duplicate_sku_validation(self):
        """Test that duplicate SKUs are caught for same vendor."""
        # Create existing product
        ProductFactory(vendor=self.vendor, sku='EXISTING')

        data = {
            'name': 'New Product',
            'category': self.category.id,
            'sku': 'EXISTING',  # Duplicate
            'price': '10.00',
            'unit': 'unit'
        }

        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={'request': type('Request', (), {'user': self.user})()}
        )

        assert not serializer.is_valid()
        assert 'sku' in serializer.errors
        assert 'already exists' in str(serializer.errors['sku'][0])

    def test_negative_price_validation(self):
        """Test that negative prices are rejected."""
        data = {
            'name': 'Test Product',
            'category': self.category.id,
            'price': '-10.00',
            'unit': 'unit'
        }

        serializer = ProductCreateUpdateSerializer(
            data=data,
            context={'request': type('Request', (), {'user': self.user})()}
        )

        assert not serializer.is_valid()
        assert 'price' in serializer.errors


@pytest.mark.django_db
class TestProductSearchSerializer:
    """Test product search parameter validation."""

    def test_valid_search_parameters(self):
        """Test valid search parameters."""
        category = CategoryFactory()
        tag = TagFactory()

        data = {
            'search': 'tomato',
            'category': category.id,
            'tags': [tag.id],
            'min_price': '5.00',
            'max_price': '50.00',
            'in_stock_only': True,
            'allergen_free': ['milk', 'eggs'],
            'dietary': ['vegan'],
            'min_fsa_rating': 4,
            'ordering': '-price'
        }

        serializer = ProductSearchSerializer(data=data)

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['min_price'] == Decimal('5.00')
        assert validated['max_price'] == Decimal('50.00')
        assert 'milk' in validated['allergen_free']

    def test_invalid_price_range(self):
        """Test that min_price cannot exceed max_price."""
        data = {
            'min_price': '50.00',
            'max_price': '10.00'
        }

        serializer = ProductSearchSerializer(data=data)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'minimum price cannot exceed maximum' in str(
            serializer.errors).lower()

    def test_invalid_fsa_rating(self):
        """Test FSA rating must be 1-5."""
        data = {'min_fsa_rating': 6}

        serializer = ProductSearchSerializer(data=data)

        assert not serializer.is_valid()
        assert 'min_fsa_rating' in serializer.errors

    def test_invalid_allergen_field(self):
        """Test that only valid allergen fields are accepted."""
        data = {'allergen_free': ['milk', 'invalid_allergen']}

        serializer = ProductSearchSerializer(data=data)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'invalid_allergen' in str(serializer.errors).lower()
