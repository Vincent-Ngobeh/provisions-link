"""
Unit tests for ProductService.
Tests product creation, search, stock management, and allergen compliance.
"""
from tests.conftest import UserFactory, VendorFactory, ProductFactory, BuyingGroupFactory
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from django.contrib.gis.geos import Point
from django.contrib.postgres.search import SearchQuery, SearchVector

from apps.products.services.product_service import ProductService
from apps.products.models import Product, Category, Tag
from apps.core.services.base import ServiceResult


class TestProductCreation:
    """Test product creation with validation."""

    @pytest.mark.django_db
    def test_create_product_success(
        self,
        product_service,
        approved_vendor,
        test_category
    ):
        """Test successful product creation with all fields."""
        # Arrange
        product_data = {
            'name': 'Organic Tomatoes',
            'description': 'Fresh organic tomatoes from local farms',
            'category_id': test_category.id,
            'sku': 'TOM-001',
            'price': Decimal('4.99'),
            'unit': 'kg',
            'stock_quantity': 100,
            'vat_rate': Decimal('0.00'),  # Zero-rated for food
            'barcode': '1234567890123',
            'contains_allergens': False,
            'primary_image': 'https://example.com/tomato.jpg',
            'additional_images': ['https://example.com/tomato2.jpg']
        }

        # Act
        result = product_service.create_product(
            vendor=approved_vendor,
            **product_data
        )

        # Assert
        assert result.success is True
        product = result.data
        assert isinstance(product, Product)
        assert product.name == 'Organic Tomatoes'
        assert product.vendor == approved_vendor
        assert product.price == Decimal('4.99')
        assert product.sku == 'TOM-001'
        assert product.is_active is True
        assert product.low_stock_threshold == 10  # Default minimum

    @pytest.mark.django_db
    def test_create_product_requires_approved_vendor(
        self,
        product_service,
        test_vendor,
        test_category
    ):
        """Test that only approved vendors can create products."""
        # Arrange
        test_vendor.is_approved = False
        test_vendor.save()

        # Act
        result = product_service.create_product(
            vendor=test_vendor,
            name='Test Product',
            description='Test',
            category_id=test_category.id,
            sku='TEST-001',
            price=Decimal('10.00'),
            unit='unit'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'VENDOR_NOT_APPROVED'

    @pytest.mark.django_db
    def test_create_product_validates_sku_uniqueness(
        self,
        product_service,
        approved_vendor,
        test_category,
        test_product
    ):
        """Test that SKU must be unique per vendor."""
        # Arrange
        test_product.vendor = approved_vendor
        test_product.sku = 'EXISTING-SKU'
        test_product.save()

        # Act - Try to create product with same SKU
        result = product_service.create_product(
            vendor=approved_vendor,
            name='Another Product',
            description='Test',
            category_id=test_category.id,
            sku='EXISTING-SKU',  # Duplicate
            price=Decimal('20.00'),
            unit='unit'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'DUPLICATE_SKU'

    @pytest.mark.django_db
    def test_create_product_validates_price_range(
        self,
        product_service,
        approved_vendor,
        test_category
    ):
        """Test price validation."""
        # Test price too low
        result = product_service.create_product(
            vendor=approved_vendor,
            name='Test Product',
            description='Test',
            category_id=test_category.id,
            sku='TEST-001',
            price=Decimal('0.00'),  # Below minimum
            unit='unit'
        )
        assert result.success is False
        assert result.error_code == 'INVALID_PRICE'

        # Test price too high
        result = product_service.create_product(
            vendor=approved_vendor,
            name='Test Product',
            description='Test',
            category_id=test_category.id,
            sku='TEST-002',
            price=Decimal('10000.00'),  # Above maximum
            unit='unit'
        )
        assert result.success is False
        assert result.error_code == 'INVALID_PRICE'

    @pytest.mark.django_db
    def test_create_product_with_allergen_info(
        self,
        product_service,
        approved_vendor,
        test_category
    ):
        """Test product creation with allergen information."""
        # Arrange
        allergen_info = {
            'milk': True,
            'eggs': True,
            'tree_nuts': False,
            'peanuts': False,
            'gluten': True
        }

        # Act
        result = product_service.create_product(
            vendor=approved_vendor,
            name='Chocolate Cake',
            description='Contains milk, eggs, and gluten',
            category_id=test_category.id,
            sku='CAKE-001',
            price=Decimal('15.99'),
            unit='unit',
            contains_allergens=True,
            allergen_info=allergen_info,
            allergen_statement='Contains: Milk, Eggs, Wheat (Gluten)'
        )

        # Assert
        assert result.success is True
        product = result.data
        assert product.contains_allergens is True
        assert product.allergen_info['milk'] is True
        assert product.allergen_info['eggs'] is True
        assert product.allergen_info['tree_nuts'] is False

        # Check all 14 allergen fields are present
        assert len(product.allergen_info) == 14


class TestProductSearch:
    """Test product search and filtering."""

    @pytest.mark.django_db
    def test_search_products_by_text(
        self,
        product_service,
        approved_vendor
    ):
        """Test full-text search functionality."""
        # Arrange
        # Create products with searchable content
        product1 = ProductFactory(
            vendor=approved_vendor,
            name='Organic Tomatoes',
            description='Fresh red tomatoes from local farms'
        )

        product2 = ProductFactory(
            vendor=approved_vendor,
            name='Cherry Tomatoes',
            description='Sweet small tomatoes perfect for salads'
        )

        product3 = ProductFactory(
            vendor=approved_vendor,
            name='Potatoes',
            description='Fresh potatoes for roasting'
        )

        # Update search vectors (normally done by signal/trigger)
        for p in [product1, product2, product3]:
            product_service._update_search_vector(p)

        # Act
        result = product_service.search_products(
            search_query='tomatoes',
            page_size=10
        )

        # Assert
        assert result.success is True
        products = result.data['products']

        # Should find products with "tomatoes" in name or description
        assert len(products) >= 2
        product_names = [p['name'] for p in products]
        assert 'Organic Tomatoes' in product_names
        assert 'Cherry Tomatoes' in product_names

    @pytest.mark.django_db
    def test_search_products_by_price_range(
        self,
        product_service,
        approved_vendor
    ):
        """Test filtering products by price range."""
        # Arrange
        cheap_product = ProductFactory(
            vendor=approved_vendor,
            price=Decimal('5.00')
        )

        medium_product = ProductFactory(
            vendor=approved_vendor,
            price=Decimal('15.00')
        )

        expensive_product = ProductFactory(
            vendor=approved_vendor,
            price=Decimal('50.00')
        )

        # Act
        result = product_service.search_products(
            min_price=Decimal('10.00'),
            max_price=Decimal('30.00')
        )

        # Assert
        assert result.success is True
        products = result.data['products']

        # Should only include medium product
        prices = [Decimal(str(p['price'])) for p in products]
        assert all(Decimal('10.00') <= p <= Decimal('30.00') for p in prices)

    @pytest.mark.django_db
    def test_search_products_allergen_free(
        self,
        product_service,
        approved_vendor
    ):
        """Test filtering products by allergen exclusion."""
        # Arrange
        # Product with milk and eggs
        dairy_product = ProductFactory(
            vendor=approved_vendor,
            name='Cheese Pizza',
            contains_allergens=True,
            allergen_info={'milk': True, 'eggs': True}
        )

        # Product with gluten only
        bread_product = ProductFactory(
            vendor=approved_vendor,
            name='Whole Wheat Bread',
            contains_allergens=True,
            allergen_info={'cereals_containing_gluten': True, 'milk': False}
        )

        # Allergen-free product
        safe_product = ProductFactory(
            vendor=approved_vendor,
            name='Fresh Apples',
            contains_allergens=False,
            allergen_info={}
        )

        # Act - Search for products without milk
        result = product_service.search_products(
            allergen_free=['milk']
        )

        # Assert
        assert result.success is True
        products = result.data['products']

        product_names = [p['name'] for p in products]
        assert 'Cheese Pizza' not in product_names  # Has milk
        assert 'Whole Wheat Bread' in product_names  # No milk
        assert 'Fresh Apples' in product_names  # No allergens

    @pytest.mark.django_db
    def test_search_products_by_location(
        self,
        product_service,
        mock_geocoding_response
    ):
        """Test location-based product search."""
        # Arrange
        # Create vendors at different locations
        nearby_vendor = VendorFactory(
            location=Point(-0.1276, 51.5074),
            delivery_radius_km=10
        )

        far_vendor = VendorFactory(
            location=Point(-1.0000, 52.0000),  # Far away
            delivery_radius_km=5
        )

        nearby_product = ProductFactory(vendor=nearby_vendor)
        far_product = ProductFactory(vendor=far_vendor)

        with patch('apps.integrations.services.geocoding_service.GeocodingService.geocode_postcode') as mock_geo:
            mock_geo.return_value = ServiceResult.ok({
                'point': Point(-0.1276, 51.5074),
                'area_name': 'Westminster'
            })

            # Act
            result = product_service.search_products(
                postcode='SW1A 1AA',
                radius_km=15
            )

        # Assert
        assert result.success is True
        # Products should be filtered by vendor location

    @pytest.mark.django_db
    def test_search_products_with_pagination(
        self,
        product_service,
        approved_vendor
    ):
        """Test search results pagination."""
        # Arrange
        # Create 25 products
        for i in range(25):
            ProductFactory(
                vendor=approved_vendor,
                name=f'Product {i:02d}'
            )

        # Act - Get first page
        result = product_service.search_products(
            page=1,
            page_size=10
        )

        # Assert
        assert result.success is True
        data = result.data

        assert len(data['products']) == 10
        assert data['count'] == 25
        assert data['next'] is not None
        assert data['previous'] is None


class TestProductStockManagement:
    """Test stock management operations."""

    @pytest.mark.django_db
    def test_update_stock_add_operation(
        self,
        product_service,
        test_product
    ):
        """Test adding stock to a product."""
        # Arrange
        test_product.stock_quantity = 50
        test_product.save()

        # Act
        result = product_service.update_stock(
            product_id=test_product.id,
            quantity_change=30,
            operation='add',
            reason='Delivery received'
        )

        # Assert
        assert result.success is True
        assert result.data['old_quantity'] == 50
        assert result.data['new_quantity'] == 80

        test_product.refresh_from_db()
        assert test_product.stock_quantity == 80

    @pytest.mark.django_db
    def test_update_stock_subtract_operation(
        self,
        product_service,
        test_product
    ):
        """Test subtracting stock from a product."""
        # Arrange
        test_product.stock_quantity = 50
        test_product.save()

        # Act
        result = product_service.update_stock(
            product_id=test_product.id,
            quantity_change=20,
            operation='subtract',
            reason='Order fulfilled'
        )

        # Assert
        assert result.success is True
        assert result.data['old_quantity'] == 50
        assert result.data['new_quantity'] == 30

    @pytest.mark.django_db
    def test_update_stock_prevents_negative(
        self,
        product_service,
        test_product
    ):
        """Test that stock cannot go negative."""
        # Arrange
        test_product.stock_quantity = 10
        test_product.save()

        # Act
        result = product_service.update_stock(
            product_id=test_product.id,
            quantity_change=15,  # More than available
            operation='subtract'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INSUFFICIENT_STOCK'

    @pytest.mark.django_db
    def test_update_stock_triggers_low_stock_alert(
        self,
        product_service,
        test_product
    ):
        """Test that low stock alert is triggered when threshold crossed."""
        # Arrange
        test_product.stock_quantity = 15
        test_product.low_stock_threshold = 10
        test_product.save()

        # Act - Reduce stock below threshold
        result = product_service.update_stock(
            product_id=test_product.id,
            quantity_change=7,
            operation='subtract'
        )

        # Assert
        assert result.success is True
        assert result.data['new_quantity'] == 8
        assert result.data['low_stock_alert'] is True
        assert result.data['out_of_stock'] is False

    @pytest.mark.django_db
    def test_get_low_stock_products(
        self,
        product_service,
        approved_vendor
    ):
        """Test retrieving products with low stock."""
        # Arrange
        # Create products with different stock levels
        low_stock = ProductFactory(
            vendor=approved_vendor,
            name='Low Stock Item',
            stock_quantity=5,
            low_stock_threshold=10
        )

        out_of_stock = ProductFactory(
            vendor=approved_vendor,
            name='Out of Stock Item',
            stock_quantity=0,
            low_stock_threshold=10
        )

        well_stocked = ProductFactory(
            vendor=approved_vendor,
            name='Well Stocked Item',
            stock_quantity=100,
            low_stock_threshold=10
        )

        # Act
        result = product_service.get_low_stock_products(
            vendor_id=approved_vendor.id
        )

        # Assert
        assert result.success is True
        products = result.data['products']

        # Should include low and out of stock items
        product_names = [p['name'] for p in products]
        assert 'Low Stock Item' in product_names
        assert 'Out of Stock Item' in product_names
        assert 'Well Stocked Item' not in product_names

        assert result.data['out_of_stock_count'] == 1


class TestProductUpdate:
    """Test product update operations."""

    @pytest.mark.django_db
    def test_update_product_success(
        self,
        product_service,
        test_product,
        approved_vendor
    ):
        """Test updating product information."""
        # Arrange
        test_product.vendor = approved_vendor
        test_product.save()

        updates = {
            'name': 'Updated Product Name',
            'description': 'New description',
            'price': Decimal('29.99'),
            'stock_quantity': 200
        }

        # Act
        result = product_service.update_product(
            product_id=test_product.id,
            vendor=approved_vendor,
            **updates
        )

        # Assert
        assert result.success is True

        test_product.refresh_from_db()
        assert test_product.name == 'Updated Product Name'
        assert test_product.description == 'New description'
        assert test_product.price == Decimal('29.99')
        assert test_product.stock_quantity == 200

    @pytest.mark.django_db
    def test_update_product_requires_ownership(
        self,
        product_service,
        test_product,
        approved_vendor
    ):
        """Test that vendors can only update their own products."""
        # Arrange
        other_vendor = VendorFactory()
        test_product.vendor = approved_vendor
        test_product.save()

        # Act - Other vendor tries to update
        result = product_service.update_product(
            product_id=test_product.id,
            vendor=other_vendor,  # Different vendor
            name='Hacked Name'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'PRODUCT_NOT_FOUND'
