"""
API tests for product endpoints.
Tests permissions, validation, and business rules.
"""
import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse

from apps.products.models import Product, Category
from tests.conftest import ProductFactory, VendorFactory, UserFactory, CategoryFactory


@pytest.mark.django_db
class TestProductListAPI:
    """Test product listing and search endpoints."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('product-list')

    def test_list_products_no_auth_required(self):
        """Test that product listing doesn't require authentication."""
        ProductFactory.create_batch(5)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 5

    def test_list_products_filters_by_vendor(self):
        """Test filtering products by vendor."""
        vendor1 = VendorFactory()
        vendor2 = VendorFactory()
        ProductFactory.create_batch(3, vendor=vendor1)
        ProductFactory.create_batch(2, vendor=vendor2)

        response = self.client.get(self.url, {'vendor': vendor1.id})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 3
        for product in response.data['results']:
            assert product['vendor']['id'] == vendor1.id

    def test_list_products_filters_by_stock(self):
        """Test filtering products by stock availability."""
        ProductFactory(stock_quantity=0)
        ProductFactory(stock_quantity=10)

        response = self.client.get(self.url, {'in_stock_only': 'true'})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 1
        assert response.data['results'][0]['in_stock'] is True

    def test_list_products_pagination(self):
        """Test product list pagination."""
        ProductFactory.create_batch(25)

        response = self.client.get(self.url, {'page_size': 10})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) <= 10
        assert 'next' in response.data
        assert response.data['count'] == 25


@pytest.mark.django_db
class TestProductCreateAPI:
    """Test product creation endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('product-list')
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user, is_approved=True)
        self.category = CategoryFactory()

    def test_unauthenticated_cannot_create_product(self):
        """Test that unauthenticated users cannot create products."""
        data = {
            'name': 'Test Product',
            'category': self.category.id,
            'price': '10.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_vendor_cannot_create_product(self):
        """Test that non-vendors cannot create products."""
        regular_user = UserFactory()
        self.client.force_authenticate(regular_user)

        data = {
            'name': 'Test Product',
            'category': self.category.id,
            'price': '10.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code in [
            status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST]

    def test_vendor_can_create_product(self):
        """Test that approved vendors can create products."""
        self.client.force_authenticate(self.vendor_user)

        data = {
            'name': 'Organic Tomatoes',
            'description': 'Fresh organic tomatoes',
            'category': self.category.id,
            'sku': 'TOM-001',
            'price': '4.99',
            'unit': 'kg',
            'stock_quantity': 100,
            'vat_rate': '0.00',
            'contains_allergens': False
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'Organic Tomatoes'
        assert Decimal(response.data['price']) == Decimal('4.99')

        # Verify product was created
        product = Product.objects.get(sku='TOM-001')
        assert product.vendor == self.vendor

    def test_create_product_validates_negative_price(self):
        """Test that negative prices are rejected."""
        self.client.force_authenticate(self.vendor_user)

        data = {
            'name': 'Test Product',
            'category': self.category.id,
            'price': '-10.00',
            'unit': 'kg'
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'price' in str(
            response.data).lower() or 'error' in response.data

    def test_create_product_validates_duplicate_sku(self):
        """Test that duplicate SKUs are rejected for same vendor."""
        self.client.force_authenticate(self.vendor_user)
        ProductFactory(vendor=self.vendor, sku='EXISTING-SKU')

        data = {
            'name': 'New Product',
            'category': self.category.id,
            'sku': 'EXISTING-SKU',
            'price': '10.00',
            'unit': 'unit'
        }

        response = self.client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'sku' in str(response.data).lower(
        ) or 'already exists' in str(response.data)


@pytest.mark.django_db
class TestProductUpdateAPI:
    """Test product update endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user)
        self.product = ProductFactory(vendor=self.vendor)
        self.url = reverse('product-detail', kwargs={'pk': self.product.id})

    def test_vendor_can_update_own_product(self):
        """Test that vendors can update their own products."""
        self.client.force_authenticate(self.vendor_user)

        data = {'price': '29.99'}

        response = self.client.patch(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        self.product.refresh_from_db()
        assert self.product.price == Decimal('29.99')

    def test_vendor_cannot_update_other_vendor_product(self):
        """Test that vendors cannot update products from other vendors."""
        other_vendor_user = UserFactory()
        other_vendor = VendorFactory(user=other_vendor_user)
        self.client.force_authenticate(other_vendor_user)

        data = {'price': '29.99'}

        response = self.client.patch(self.url, data)

        assert response.status_code in [
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

    def test_update_stock_endpoint(self):
        """Test the update_stock custom action."""
        self.client.force_authenticate(self.vendor_user)
        url = reverse('product-update-stock', kwargs={'pk': self.product.id})

        self.product.stock_quantity = 50
        self.product.save()

        data = {
            'quantity_change': 20,
            'operation': 'add',
            'reason': 'New delivery'
        }

        response = self.client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['new_quantity'] == 70

        self.product.refresh_from_db()
        assert self.product.stock_quantity == 70


@pytest.mark.django_db
class TestProductSearchAPI:
    """Test advanced product search endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('product-search')
        self.vendor = VendorFactory(fsa_rating_value=5)

    def test_search_products_by_text(self):
        """Test searching products by name/description."""
        ProductFactory(vendor=self.vendor, name='Organic Tomatoes')
        ProductFactory(vendor=self.vendor, name='Fresh Potatoes')

        data = {'search': 'tomato'}

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['pagination']['total_products'] >= 1
        assert any('tomato' in p['name'].lower()
                   for p in response.data['products'])

    def test_search_products_by_price_range(self):
        """Test filtering products by price range."""
        ProductFactory(vendor=self.vendor, price=Decimal('5.00'))
        ProductFactory(vendor=self.vendor, price=Decimal('15.00'))
        ProductFactory(vendor=self.vendor, price=Decimal('50.00'))

        data = {
            'min_price': '10.00',
            'max_price': '30.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        for product in response.data['products']:
            price = Decimal(product['price'])
            assert Decimal('10.00') <= price <= Decimal('30.00')

    def test_search_validates_price_range(self):
        """Test that invalid price ranges are rejected."""
        data = {
            'min_price': '50.00',
            'max_price': '10.00'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'minimum price cannot exceed maximum' in str(
            response.data).lower()


@pytest.mark.django_db
class TestProductPermissions:
    """Test product endpoint permissions."""

    def setup_method(self):
        self.client = APIClient()
        self.vendor_user = UserFactory()
        self.vendor = VendorFactory(user=self.vendor_user)
        self.product = ProductFactory(vendor=self.vendor)

        self.other_user = UserFactory()
        self.staff_user = UserFactory(is_staff=True)

    def test_delete_product_requires_ownership(self):
        """Test that only product owner or staff can delete."""
        url = reverse('product-detail', kwargs={'pk': self.product.id})

        # Other user cannot delete
        self.client.force_authenticate(self.other_user)
        response = self.client.delete(url)
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]

        # Owner can delete
        self.client.force_authenticate(self.vendor_user)
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify product is soft-deleted
        self.product.refresh_from_db()
        assert self.product.is_active is False
