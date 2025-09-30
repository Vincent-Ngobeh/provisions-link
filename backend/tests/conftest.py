"""
Pytest configuration and fixtures for Provisions Link tests.
Provides reusable test fixtures for models, services, and common test data.
"""
from apps.products.models import Product, Category, Tag
from apps.vendors.models import Vendor
from apps.core.models import User, Address, PrivacySettings
from apps.orders.models import Order, OrderItem
from faker import Faker
from factory.django import DjangoModelFactory
import factory
from django.test import override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import os
import sys
import django

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure Django settings before any Django imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE',
                      'provisions_link.settings.test')
django.setup()

# Now safe to import Django and third-party modules


# Import models

# Try to import GIS-dependent models
try:
    from apps.buying_groups.models import BuyingGroup, GroupCommitment
    HAS_GIS = True
except ImportError:
    # Create mock classes for tests that don't need actual GIS functionality
    HAS_GIS = False

    class BuyingGroup:
        pass

    class GroupCommitment:
        pass

# Initialize Faker for realistic test data
fake = Faker('en_GB')  # Use UK locale for UK-specific data


# Helper function for Point objects
def get_point_class():
    """Get Point class or mock if GIS unavailable."""
    try:
        from django.contrib.gis.geos import Point
        return Point
    except ImportError:
        # Return a mock Point class for non-GIS tests
        class MockPoint:
            def __init__(self, x, y):
                self.x = x
                self.y = y
                self.coords = (x, y)

            def distance(self, other):
                # Simple Euclidean distance for testing
                from math import sqrt
                dx = self.x - other.x
                dy = self.y - other.y
                return sqrt(dx*dx + dy*dy)

        return MockPoint


# ==================== Factory Classes ====================

class UserFactory(DjangoModelFactory):
    """Factory for creating test users."""

    class Meta:
        model = User
        skip_postgeneration_save = True  # Fix for deprecation warning

    email = factory.Faker('email')
    username = factory.Sequence(lambda n: f'user{n}')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    phone_number = factory.LazyAttribute(
        lambda _: f"+44{fake.numerify('##########')}")
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.set_password(extracted)
        else:
            self.set_password('testpass123')
        self.save()  # Save after setting password


class AddressFactory(DjangoModelFactory):
    """Factory for creating test addresses."""

    class Meta:
        model = Address

    user = factory.SubFactory(UserFactory)
    address_name = factory.Faker('random_element', elements=[
                                 'home', 'work', 'other'])
    recipient_name = factory.Faker('name')
    phone_number = factory.LazyAttribute(
        lambda _: f"+44{fake.numerify('##########')}")
    line1 = factory.Faker('street_address')
    line2 = factory.Faker('secondary_address')
    city = factory.Faker('city')
    postcode = factory.LazyAttribute(lambda _: fake.postcode())
    country = 'GB'
    is_default = False

    # Always create location since we're in Docker with GIS
    location = factory.LazyAttribute(
        lambda _: get_point_class()(-0.1276, 51.5074)
    )


class VendorFactory(DjangoModelFactory):
    """Factory for creating test vendors."""

    class Meta:
        model = Vendor

    user = factory.SubFactory(UserFactory)
    business_name = factory.LazyAttribute(
        lambda _: fake.company()[:200])  # Ensure max 200 chars
    slug = factory.LazyAttribute(
        lambda _: fake.slug()[:250])  # Ensure max 250 chars
    description = factory.Faker('text', max_nb_chars=500)
    phone_number = factory.LazyAttribute(
        # Ensure max 17 chars
        lambda _: f"+44{fake.numerify('##########')}"[:17])

    # Approval and verification
    is_approved = True
    fsa_verified = True
    stripe_onboarding_complete = True

    # Location fields
    postcode = factory.LazyAttribute(lambda _: fake.postcode())
    delivery_radius_km = 10

    # Always create location since we're in Docker with GIS
    location = factory.LazyAttribute(
        lambda _: get_point_class()(-0.1276, 51.5074)
    )

    # FSA Integration
    fsa_establishment_id = factory.LazyAttribute(
        lambda _: fake.numerify('FSA-####-####'))  # Max 20 chars
    fsa_rating_value = factory.Faker('random_int', min=3, max=5)
    fsa_rating_date = factory.LazyAttribute(lambda _: timezone.now().date())
    fsa_last_checked = factory.LazyAttribute(lambda _: timezone.now())

    # Stripe
    stripe_account_id = factory.LazyAttribute(
        lambda _: f"acct_{fake.uuid4()[:16]}")
    commission_rate = Decimal('0.10')

    # Business details
    vat_number = factory.LazyAttribute(
        # Ensure max 20 chars
        lambda _: f"GB{fake.numerify('#########')}"[:20])
    min_order_value = Decimal('50.00')
    logo_url = factory.Faker('image_url')


class CategoryFactory(DjangoModelFactory):
    """Factory for creating test categories."""

    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f'Category-{n}')
    slug = factory.Sequence(lambda n: f'category-{n}')
    parent = None
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class TagFactory(DjangoModelFactory):
    """Factory for creating test tags."""

    class Meta:
        model = Tag

    name = factory.Faker('word')
    slug = factory.Faker('slug')
    tag_type = factory.Faker('random_element', elements=[
                             'dietary', 'organic', 'origin', 'other'])


class ProductFactory(DjangoModelFactory):
    """Factory for creating test products."""

    class Meta:
        model = Product

    vendor = factory.SubFactory(VendorFactory)
    category = factory.SubFactory(CategoryFactory)

    name = factory.Faker('catch_phrase')
    slug = factory.Faker('slug')
    description = factory.Faker('text', max_nb_chars=1000)
    sku = factory.LazyAttribute(lambda _: fake.bothify('???-####'))
    barcode = factory.LazyAttribute(lambda _: fake.ean13())

    # Pricing
    price = factory.Faker('pydecimal', left_digits=3, right_digits=2,
                          positive=True, min_value=1, max_value=500)
    vat_rate = Decimal('0.20')
    unit = factory.Faker('random_element', elements=[
                         'kg', 'g', 'l', 'ml', 'unit'])

    # Stock
    stock_quantity = factory.Faker('random_int', min=10, max=500)
    low_stock_threshold = 10

    # Allergens
    contains_allergens = False
    allergen_info = {}
    allergen_statement = ''

    # Media
    primary_image = factory.Faker('image_url')
    additional_images = []

    # Status
    is_active = True
    featured = False


class OrderFactory(DjangoModelFactory):
    """Factory for creating test orders."""

    class Meta:
        model = Order
        django_get_or_create = ('reference_number',)

    reference_number = factory.Sequence(
        lambda n: f"PL-{timezone.now().year}-{fake.bothify('?????').upper()}-{n}"
    )
    buyer = factory.SubFactory(UserFactory)
    vendor = factory.SubFactory(VendorFactory)
    delivery_address = factory.SubFactory(AddressFactory)
    group = None

    subtotal = Decimal('100.00')
    vat_amount = Decimal('20.00')
    delivery_fee = Decimal('5.00')
    total = Decimal('125.00')
    marketplace_fee = Decimal('10.00')
    vendor_payout = Decimal('115.00')

    stripe_payment_intent_id = factory.LazyAttribute(
        lambda _: f"pi_{fake.uuid4()[:24]}"
    )

    delivery_notes = ''
    status = 'pending'
    paid_at = None
    delivered_at = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override create to allow explicit created_at bypass of auto_now_add."""
        # Extract created_at if provided, otherwise use current time
        custom_created_at = kwargs.pop('created_at', None)

        # Create object normally (auto_now_add will set created_at)
        obj = model_class(*args, **kwargs)
        obj.save()

        # If custom created_at was provided, update it using queryset.update()
        # This bypasses auto_now_add
        if custom_created_at is not None:
            model_class.objects.filter(pk=obj.pk).update(
                created_at=custom_created_at)
            obj.refresh_from_db()

        return obj


class OrderItemFactory(DjangoModelFactory):
    """Factory for creating test order items."""

    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    product = factory.SubFactory(ProductFactory)
    quantity = factory.Faker('random_int', min=1, max=10)
    unit_price = Decimal('20.00')
    total_price = Decimal('100.00')
    discount_amount = Decimal('0.00')


# GIS-dependent factories
if HAS_GIS:
    class BuyingGroupFactory(DjangoModelFactory):
        """Factory for creating test buying groups."""

        class Meta:
            model = BuyingGroup

        product = factory.SubFactory(ProductFactory)
        center_point = factory.LazyAttribute(
            lambda _: get_point_class()(-0.1276, 51.5074))
        radius_km = 5
        area_name = factory.LazyAttribute(lambda _: f"{fake.city()} area")

        target_quantity = 50
        current_quantity = 0
        min_quantity = 30
        discount_percent = Decimal('15.00')

        expires_at = factory.LazyAttribute(
            lambda _: timezone.now() + timedelta(days=7))

        status = 'open'

        @classmethod
        def _create(cls, model_class, *args, **kwargs):
            """Override create to allow explicit created_at bypass of auto_now_add."""
            # Extract created_at if provided
            custom_created_at = kwargs.pop('created_at', None)

            # Create object normally
            obj = model_class(*args, **kwargs)
            obj.save()

            # Update created_at using queryset.update() to bypass auto_now_add
            if custom_created_at is not None:
                model_class.objects.filter(pk=obj.pk).update(
                    created_at=custom_created_at)
                obj.refresh_from_db()

            return obj

    class GroupCommitmentFactory(DjangoModelFactory):
        """Factory for creating test group commitments."""

        class Meta:
            model = GroupCommitment

        group = factory.SubFactory(BuyingGroupFactory)
        buyer = factory.SubFactory(UserFactory)
        quantity = factory.Faker('random_int', min=1, max=10)

        buyer_location = factory.LazyAttribute(
            lambda _: get_point_class()(-0.1276, 51.5074))
        buyer_postcode = factory.LazyAttribute(lambda _: fake.postcode())

        stripe_payment_intent_id = factory.LazyAttribute(
            lambda _: f"pi_{fake.uuid4()[:24]}")

        status = 'pending'


# ==================== Pytest Fixtures ====================

@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Override django_db_setup to configure test database.
    """
    with django_db_blocker.unblock():
        # Any global test database setup here
        pass


@pytest.fixture
def test_user(db):
    """Create a test user."""
    user = UserFactory()
    user.raw_password = 'testpass123'  # Store raw password for login tests
    return user


@pytest.fixture
def test_vendor(db, test_user):
    """Create a test vendor with associated user."""
    return VendorFactory(user=test_user)


@pytest.fixture
def approved_vendor(db):
    """Create an approved vendor ready for selling."""
    return VendorFactory(
        is_approved=True,
        fsa_verified=True,
        stripe_onboarding_complete=True,
        fsa_rating_value=5
    )


@pytest.fixture
def test_product(db, approved_vendor):
    """Create a test product."""
    return ProductFactory(vendor=approved_vendor)


@pytest.fixture
def test_category(db):
    """Create a test category."""
    return CategoryFactory(name='Food & Beverages')


@pytest.fixture
def test_address(db, test_user):
    """Create a test address."""
    return AddressFactory(user=test_user, is_default=True)


@pytest.fixture
def test_buying_group(db, test_product):
    """Create a test buying group (only if GIS available)."""
    if HAS_GIS:
        return BuyingGroupFactory(
            product=test_product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            discount_percent=Decimal('15.00')
        )
    else:
        pytest.skip("GIS not available for buying groups")


# ==================== Service Fixtures ====================

@pytest.fixture
def fsa_service():
    """Create FSAService instance."""
    from apps.integrations.services.fsa_service import FSAService
    return FSAService()


@pytest.fixture
def vendor_service():
    """Create VendorService instance."""
    from apps.vendors.services.vendor_service import VendorService
    return VendorService()


@pytest.fixture
def product_service():
    """Create ProductService instance."""
    from apps.products.services.product_service import ProductService
    return ProductService()


@pytest.fixture
def geocoding_service():
    """Create GeocodingService instance."""
    from apps.integrations.services.geocoding_service import GeocodingService
    return GeocodingService()


@pytest.fixture
def stripe_service():
    """Create StripeConnectService instance."""
    from apps.integrations.services.stripe_service import StripeConnectService
    return StripeConnectService()


@pytest.fixture
def group_buying_service():
    """Create GroupBuyingService instance (only if GIS available)."""
    if HAS_GIS:
        from apps.buying_groups.services.group_buying_service import GroupBuyingService
        return GroupBuyingService()
    else:
        pytest.skip("GIS not available for group buying service")


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_stripe_payment_intent(mocker):
    """Mock Stripe payment intent creation."""
    mock = mocker.patch('stripe.PaymentIntent.create')
    mock.return_value = mocker.MagicMock(
        id='pi_test_123456789',
        client_secret='pi_test_123456789_secret',
        amount=10000,
        status='requires_payment_method'
    )
    return mock


@pytest.fixture
def mock_geocoding_response(mocker):
    """Mock geocoding service response."""
    mock = mocker.patch(
        'apps.integrations.services.geocoding_service.GeocodingService.geocode_postcode'
    )
    from apps.core.services.base import ServiceResult
    mock.return_value = ServiceResult.ok({
        'point': get_point_class()(-0.1276, 51.5074),
        'lng': -0.1276,
        'lat': 51.5074,
        'area_name': 'Westminster',
        'confidence': 0.9,
        'provider': 'mock'
    })
    return mock


@pytest.fixture
def mock_fsa_search(mocker):
    """Mock FSA API search response."""
    mock = mocker.patch(
        'apps.integrations.services.fsa_service.FSAService.search_establishment'
    )
    from apps.core.services.base import ServiceResult
    mock.return_value = ServiceResult.ok([
        {
            'fsa_id': 'TEST-FSA-123',
            'business_name': 'Test Restaurant',
            'rating_value': 5,
            'rating_date': timezone.now().date(),
            'postcode': 'SW1A 1AA'
        }
    ])
    return mock


# ==================== Test Data Fixtures ====================

@pytest.fixture
def sample_product_data():
    """Sample data for creating a product."""
    return {
        'name': 'Organic Tomatoes',
        'description': 'Fresh organic tomatoes from local farms',
        'sku': 'TOM-001',
        'price': Decimal('4.99'),
        'unit': 'kg',
        'stock_quantity': 100,
        'contains_allergens': False,
        'allergen_info': {}
    }


@pytest.fixture
def sample_vendor_data():
    """Sample data for vendor registration."""
    return {
        'business_name': 'Fresh Foods Ltd',
        'description': 'Premium fresh food supplier',
        'postcode': 'SW1A 1AA',
        'delivery_radius_km': 15,
        'min_order_value': Decimal('75.00'),
        'phone_number': '+442012345678',
        'vat_number': 'GB123456789'
    }


# ==================== Helper Functions ====================

def create_products_with_stock(vendor, count=5, low_stock=False):
    """Helper to create multiple products with varying stock levels."""
    products = []
    for i in range(count):
        stock = 5 if low_stock else 100
        product = ProductFactory(
            vendor=vendor,
            name=f"Product {i+1}",
            stock_quantity=stock,
            low_stock_threshold=10
        )
        products.append(product)
    return products


def create_buying_group_with_commitments(product, num_commitments=3):
    """Helper to create a buying group with commitments (GIS only)."""
    if not HAS_GIS:
        pytest.skip("GIS not available for buying groups")

    group = BuyingGroupFactory(product=product)
    commitments = []

    for _ in range(num_commitments):
        commitment = GroupCommitmentFactory(
            group=group,
            quantity=10
        )
        commitments.append(commitment)
        group.current_quantity += commitment.quantity

    group.save()
    return group, commitments


# ==================== Settings Override Fixtures ====================

@pytest.fixture
def disable_stripe_webhooks(settings):
    """Disable Stripe webhooks for testing."""
    settings.STRIPE_WEBHOOK_SECRET = None
    return settings


@pytest.fixture
def test_cache_settings(settings):
    """Use local memory cache for testing."""
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    return settings


@pytest.fixture
def test_media_storage(settings, tmp_path):
    """Use temporary directory for media files during tests."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


# ==================== Additional Test Fixtures ====================

@pytest.fixture
def mock_pytest_mocker():
    """Provide pytest-mock mocker if needed."""
    import pytest_mock
    return pytest_mock.MockerFixture()
