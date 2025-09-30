"""
Unit tests for VendorService.
Tests vendor registration, approval, analytics, and location-based operations.
"""
from tests.conftest import UserFactory, VendorFactory, ProductFactory, OrderFactory, BuyingGroupFactory, AddressFactory
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.utils import timezone
from django.contrib.gis.geos import Point

from apps.vendors.services.vendor_service import VendorService
from apps.orders.models import Order, OrderItem
from apps.vendors.models import Vendor
from apps.core.services.base import ServiceResult


class TestVendorRegistration:
    """Test vendor registration and onboarding."""

    @pytest.mark.django_db
    def test_register_vendor_success(
        self,
        vendor_service,
        test_user,
        mock_geocoding_response,
        mock_fsa_search
    ):
        """Test successful vendor registration with FSA verification."""
        # Arrange
        vendor_data = {
            'business_name': 'Test Restaurant Ltd',
            'description': 'Fine dining establishment',
            'postcode': 'SW1A 1AA',
            'delivery_radius_km': 10,
            'min_order_value': Decimal('50.00'),
            'phone_number': '+442012345678',
            'vat_number': 'GB123456789'
        }

        mock_stripe_result = ServiceResult.ok({
            'account_id': 'acct_test123',
            'onboarding_url': 'https://connect.stripe.com/onboard/test'
        })

        with patch('apps.integrations.services.stripe_service.StripeConnectService.create_vendor_account') as mock_stripe:
            mock_stripe.return_value = mock_stripe_result

            # Act
            result = vendor_service.register_vendor(
                user=test_user,
                **vendor_data
            )

        # Assert
        assert result.success is True
        data = result.data

        vendor = data['vendor']
        assert isinstance(vendor, Vendor)
        assert vendor.business_name == 'Test Restaurant Ltd'
        assert vendor.user == test_user
        assert vendor.is_approved is False  # Requires admin approval
        assert vendor.fsa_verified is True  # FSA found a match
        assert vendor.fsa_rating_value == 5
        assert vendor.commission_rate == Decimal('0.10')  # Default 10%

        assert data['onboarding_url'] == 'https://connect.stripe.com/onboard/test'
        assert data['needs_approval'] is True

    @pytest.mark.django_db
    def test_register_vendor_prevents_duplicate(
        self,
        vendor_service,
        test_user,
        test_vendor
    ):
        """Test that users cannot register multiple vendor accounts."""
        # Arrange - test_user already has test_vendor

        # Act
        result = vendor_service.register_vendor(
            user=test_user,
            business_name='Another Business',
            description='Test',
            postcode='SW1A 1AA',
            delivery_radius_km=5,
            min_order_value=Decimal('25.00')
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'VENDOR_EXISTS'

    @pytest.mark.django_db
    def test_register_vendor_validates_business_name_uniqueness(
        self,
        vendor_service,
        test_vendor
    ):
        """Test that business names must be unique."""
        # Arrange
        new_user = UserFactory()

        # Act - Try to use same business name as test_vendor
        result = vendor_service.register_vendor(
            user=new_user,
            business_name=test_vendor.business_name,
            description='Different business',
            postcode='SW1A 2AA',
            delivery_radius_km=10,
            min_order_value=Decimal('50.00')
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'BUSINESS_NAME_EXISTS'

    @pytest.mark.django_db
    def test_register_vendor_validates_delivery_radius(
        self,
        vendor_service,
        test_user
    ):
        """Test that delivery radius must be within limits."""
        # Test radius too small
        result = vendor_service.register_vendor(
            user=test_user,
            business_name='Test Business',
            description='Test',
            postcode='SW1A 1AA',
            delivery_radius_km=0,  # Below minimum
            min_order_value=Decimal('50.00')
        )
        assert result.success is False
        assert result.error_code == 'INVALID_RADIUS'

        # Test radius too large
        result = vendor_service.register_vendor(
            user=test_user,
            business_name='Test Business',
            description='Test',
            postcode='SW1A 1AA',
            delivery_radius_km=51,  # Above maximum
            min_order_value=Decimal('50.00')
        )
        assert result.success is False
        assert result.error_code == 'INVALID_RADIUS'

    @pytest.mark.django_db
    def test_register_vendor_handles_fsa_not_found(
        self,
        vendor_service,
        test_user,
        mock_geocoding_response
    ):
        """Test vendor registration when FSA establishment not found."""
        # Arrange
        mock_fsa = Mock()
        mock_fsa.success = False

        with patch('apps.vendors.services.vendor_service.VendorService._initiate_fsa_verification') as mock_fsa_init:
            mock_fsa_init.return_value = ServiceResult.fail(
                'No match', 'NO_FSA_MATCH')

            with patch('apps.integrations.services.stripe_service.StripeConnectService.create_vendor_account') as mock_stripe:
                mock_stripe.return_value = ServiceResult.ok(
                    {'account_id': 'acct_test'})

                # Act
                result = vendor_service.register_vendor(
                    user=test_user,
                    business_name='New Startup Restaurant',
                    description='Brand new',
                    postcode='SW1A 1AA',
                    delivery_radius_km=10,
                    min_order_value=Decimal('50.00')
                )

        # Assert
        assert result.success is True
        vendor = result.data['vendor']
        assert vendor.fsa_verified is False
        assert vendor.fsa_rating_value is None


class TestVendorApproval:
    """Test vendor approval process."""

    @pytest.mark.django_db
    def test_approve_vendor_by_admin(
        self,
        vendor_service,
        test_vendor
    ):
        """Test admin can approve vendors."""
        # Arrange
        admin_user = UserFactory(is_staff=True)
        test_vendor.is_approved = False
        test_vendor.fsa_rating_value = 4
        test_vendor.fsa_verified = True
        test_vendor.save()

        # Act
        result = vendor_service.approve_vendor(
            vendor_id=test_vendor.id,
            admin_user=admin_user,
            commission_rate=Decimal('0.12')  # Custom 12% commission
        )

        # Assert
        assert result.success is True

        test_vendor.refresh_from_db()
        assert test_vendor.is_approved is True
        assert test_vendor.commission_rate == Decimal('0.12')

    @pytest.mark.django_db
    def test_approve_vendor_requires_minimum_fsa_rating(
        self,
        vendor_service,
        test_vendor
    ):
        """Test that vendors need minimum FSA rating for approval."""
        # Arrange
        admin_user = UserFactory(is_staff=True)
        test_vendor.is_approved = False
        test_vendor.fsa_verified = True
        test_vendor.fsa_rating_value = 2  # Below minimum of 3
        test_vendor.save()

        # Act
        result = vendor_service.approve_vendor(
            vendor_id=test_vendor.id,
            admin_user=admin_user
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'FSA_RATING_TOO_LOW'

    @pytest.mark.django_db
    def test_approve_vendor_validates_commission_rate(
        self,
        vendor_service,
        test_vendor
    ):
        """Test commission rate validation during approval."""
        # Arrange
        admin_user = UserFactory(is_staff=True)
        test_vendor.is_approved = False
        test_vendor.save()

        # Act - Commission too high
        result = vendor_service.approve_vendor(
            vendor_id=test_vendor.id,
            admin_user=admin_user,
            commission_rate=Decimal('0.35')  # 35% exceeds maximum
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INVALID_COMMISSION'

    @pytest.mark.django_db
    def test_only_staff_can_approve_vendors(
        self,
        vendor_service,
        test_vendor,
        test_user
    ):
        """Test that only staff users can approve vendors."""
        # Arrange
        test_vendor.is_approved = False
        test_vendor.save()

        # Act - Non-staff user tries to approve
        result = vendor_service.approve_vendor(
            vendor_id=test_vendor.id,
            admin_user=test_user  # Not staff
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'PERMISSION_DENIED'


class TestVendorDashboard:
    """Test vendor dashboard metrics and analytics."""

    @pytest.mark.django_db
    def test_get_vendor_dashboard_metrics(
        self,
        vendor_service
    ):
        """Test dashboard metrics calculation."""
        # Arrange - Create isolated vendor for this test only
        isolated_vendor = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=5
        )

        # Create orders for today with explicit buyers and addresses
        buyer1 = UserFactory()
        address1 = AddressFactory(user=buyer1)
        today_order = OrderFactory(
            vendor=isolated_vendor,
            buyer=buyer1,
            delivery_address=address1,
            status='paid',
            vendor_payout=Decimal('90.00'),
            created_at=timezone.now()
        )

        # Create orders for this week
        buyer2 = UserFactory()
        address2 = AddressFactory(user=buyer2)
        week_order = OrderFactory(
            vendor=isolated_vendor,
            buyer=buyer2,
            delivery_address=address2,
            status='delivered',
            vendor_payout=Decimal('150.00'),
            created_at=timezone.now() - timedelta(days=2)
        )

        # Create pending order
        buyer3 = UserFactory()
        address3 = AddressFactory(user=buyer3)
        pending_order = OrderFactory(
            vendor=isolated_vendor,
            buyer=buyer3,
            delivery_address=address3,
            status='processing',
            created_at=timezone.now() - timedelta(days=1)
        )

        # Create low stock product
        low_stock_product = ProductFactory(
            vendor=isolated_vendor,
            stock_quantity=5,
            low_stock_threshold=10
        )

        # Create out of stock product
        out_of_stock_product = ProductFactory(
            vendor=isolated_vendor,
            stock_quantity=0
        )

        # Act
        result = vendor_service.get_vendor_dashboard_metrics(
            vendor_id=isolated_vendor.id
        )

        # Assert
        assert result.success is True
        metrics = result.data

        # Check summary metrics
        assert metrics['summary']['today_revenue'] == 90.0
        assert metrics['summary']['today_orders'] == 1
        assert metrics['summary']['pending_orders'] == 2
        # Both low and out of stock
        assert metrics['summary']['low_stock_products'] == 2
        assert metrics['summary']['out_of_stock'] == 1

        # Check vendor status
        assert metrics['vendor_status']['is_approved'] is True
        assert metrics['vendor_status']['commission_rate'] == 10.0  # 10%

    @pytest.mark.django_db
    def test_dashboard_calculates_repeat_customers(
        self,
        vendor_service
    ):
        """Test calculation of repeat customer metrics."""
        # Arrange - Create isolated vendor
        isolated_vendor = VendorFactory(is_approved=True)

        customer1 = UserFactory()
        customer2 = UserFactory()

        # Customer 1 has 3 orders (repeat customer)
        for _ in range(3):
            OrderFactory(
                vendor=isolated_vendor,
                buyer=customer1,
                status='delivered'
            )

        # Customer 2 has 1 order (new customer)
        OrderFactory(
            vendor=isolated_vendor,
            buyer=customer2,
            status='delivered'
        )

        # Act
        result = vendor_service.get_vendor_dashboard_metrics(
            vendor_id=isolated_vendor.id
        )

        # Assert
        assert result.success is True
        metrics = result.data

        assert metrics['customers']['total'] == 2
        assert metrics['customers']['repeat'] == 1  # Only customer1
        assert metrics['customers']['repeat_rate'] == 50.0  # 1 of 2


class TestVendorLocationSearch:
    """Test location-based vendor search."""

    @pytest.mark.django_db
    def test_search_vendors_by_location(
        self,
        vendor_service,
        mock_geocoding_response
    ):
        """Test finding vendors that deliver to a location."""
        # Arrange
        # Create vendors at different distances
        vendor1 = VendorFactory(
            location=Point(-0.1276, 51.5074),  # Same location
            delivery_radius_km=10,
            is_approved=True,
            fsa_rating_value=5
        )

        vendor2 = VendorFactory(
            location=Point(-0.1376, 51.5174),  # ~1km away
            delivery_radius_km=15,
            is_approved=True,
            fsa_rating_value=4
        )

        vendor3 = VendorFactory(
            location=Point(-0.2000, 51.6000),  # Far away
            delivery_radius_km=5,
            is_approved=True
        )

        with patch('apps.integrations.services.geocoding_service.GeocodingService.calculate_distance') as mock_distance:
            # Mock distances for each vendor
            mock_distance.side_effect = [
                Decimal('0.0'),   # vendor1 - same location
                Decimal('1.0'),   # vendor2 - 1km away
                Decimal('20.0'),  # vendor3 - too far
            ]

            # Act
            result = vendor_service.search_vendors_by_location(
                postcode='SW1A 1AA',
                radius_km=10,
                min_rating=4
            )

        # Assert
        assert result.success is True
        vendors = result.data['vendors']

        # Should only include vendors 1 and 2 (vendor3 too far)
        assert len(vendors) == 2
        assert vendors[0]['distance_km'] == 0.0  # Closest first
        assert vendors[1]['distance_km'] == 1.0

    @pytest.mark.django_db
    def test_search_vendors_filters_by_category(
        self,
        vendor_service,
        mock_geocoding_response,
        test_category
    ):
        """Test filtering vendors by product category."""
        # Arrange
        vendor_with_category = VendorFactory(
            location=Point(-0.1276, 51.5074),
            delivery_radius_km=10,
            is_approved=True
        )

        # Create product in category
        ProductFactory(
            vendor=vendor_with_category,
            category=test_category,
            is_active=True
        )

        vendor_without_category = VendorFactory(
            location=Point(-0.1276, 51.5074),
            delivery_radius_km=10,
            is_approved=True
        )

        with patch('apps.integrations.services.geocoding_service.GeocodingService.calculate_distance') as mock_distance:
            mock_distance.return_value = Decimal('0.0')

            # Act
            result = vendor_service.search_vendors_by_location(
                postcode='SW1A 1AA',
                category_id=test_category.id
            )

        # Assert
        assert result.success is True
        vendors = result.data['vendors']

        # Should only include vendor with products in category
        assert len(vendors) == 1
        assert vendors[0]['id'] == vendor_with_category.id


class TestVendorPerformanceReports:
    """Test vendor performance reporting."""

    @pytest.mark.django_db
    def test_get_vendor_performance_report(
        self,
        vendor_service
    ):
        """Test generating performance report for date range."""
        # Arrange - Create isolated vendor
        isolated_vendor = VendorFactory(is_approved=True)

        date_from = timezone.now() - timedelta(days=30)
        date_to = timezone.now()

        # Create successful orders with explicit data
        for i in range(3):
            buyer = UserFactory()
            address = AddressFactory(user=buyer)
            order = OrderFactory(
                vendor=isolated_vendor,
                buyer=buyer,
                delivery_address=address,
                status='delivered',
                vendor_payout=Decimal('100.00'),
                marketplace_fee=Decimal('10.00'),
                total=Decimal('110.00'),
                subtotal=Decimal('100.00'),
                created_at=date_from + timedelta(days=i*10)
            )
            OrderItem.objects.create(
                order=order,
                product=ProductFactory(vendor=isolated_vendor),
                quantity=5,
                unit_price=Decimal('20.00'),
                total_price=Decimal('100.00')
            )

        # Create cancelled order
        cancelled_order = OrderFactory(
            vendor=isolated_vendor,
            status='cancelled',
            created_at=date_from + timedelta(days=15)
        )

        # Act
        result = vendor_service.get_vendor_performance_report(
            vendor_id=isolated_vendor.id,
            date_from=date_from,
            date_to=date_to
        )

        # Assert
        assert result.success is True
        report = result.data

        # Check revenue metrics
        assert report['revenue']['total'] == 300.0  # 3 * 100
        assert report['revenue']['orders'] == 3
        assert report['revenue']['average_order'] >= 100.0
        assert report['revenue']['commission_paid'] == 30.0  # 3 * 10

        # Check fulfillment metrics
        assert report['fulfillment']['total_orders'] == 4
        assert report['fulfillment']['delivered'] == 3
        assert report['fulfillment']['cancelled'] == 1
        assert report['fulfillment']['fulfillment_rate'] == 75.0  # 3/4

    @pytest.mark.django_db
    def test_performance_report_includes_group_buying(
        self,
        vendor_service
    ):
        """Test that performance report includes group buying statistics."""
        # Arrange - Create isolated vendor and product
        isolated_vendor = VendorFactory(is_approved=True)
        test_product = ProductFactory(vendor=isolated_vendor)

        date_from = timezone.now() - timedelta(days=7)
        date_to = timezone.now()

        # Create successful group with timezone-aware datetime
        successful_group = BuyingGroupFactory(
            product=test_product,
            status='completed',
            created_at=timezone.now() - timedelta(days=6)  # Within range
        )

        # Create failed group with timezone-aware datetime
        failed_group = BuyingGroupFactory(
            product=test_product,
            status='failed',
            created_at=timezone.now() - timedelta(days=5)  # Within range
        )

        # Act
        result = vendor_service.get_vendor_performance_report(
            vendor_id=isolated_vendor.id,
            date_from=date_from,
            date_to=date_to
        )

        # Assert
        assert result.success is True
        report = result.data

        assert report['group_buying']['total_groups'] == 2
        assert report['group_buying']['successful'] == 1
        assert report['group_buying']['failed'] == 1
