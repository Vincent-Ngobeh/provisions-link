"""
Unit tests for vendor Celery tasks.
Tests FSA rating updates, compliance checks, and commission adjustments.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call

from django.utils import timezone
from django.db import models

from apps.vendors.tasks import (
    bulk_update_fsa_ratings,
    check_vendor_compliance,
    update_vendor_commission_rates,
    calculate_vendor_analytics
)
from apps.vendors.models import Vendor
from apps.orders.models import Order
from tests.conftest import VendorFactory, UserFactory, OrderFactory, ProductFactory


@pytest.mark.django_db
class TestBulkUpdateFSARatings:
    """Test bulk FSA rating update task."""

    def test_update_fsa_ratings_for_all_vendors(self):
        """Test updating FSA ratings for all vendors needing updates."""
        # Create vendors with different update requirements
        vendor_needs_update = VendorFactory(
            fsa_establishment_id='FSA-123',
            fsa_last_checked=timezone.now() - timedelta(days=10),
            fsa_rating_value=4
        )

        vendor_never_checked = VendorFactory(
            fsa_establishment_id='FSA-456',
            fsa_last_checked=None,
            fsa_rating_value=None
        )

        vendor_recently_checked = VendorFactory(
            fsa_establishment_id='FSA-789',
            fsa_last_checked=timezone.now() - timedelta(days=3),
            fsa_rating_value=5
        )

        mock_fsa_response = {
            'FSA-123': {'rating_value': 5, 'rating_date': datetime.now().date()},
            'FSA-456': {'rating_value': 4, 'rating_date': datetime.now().date()}
        }

        with patch('apps.integrations.services.fsa_service.FSAService.update_vendor_rating') as mock_update:
            def side_effect(vendor_id):
                vendor = Vendor.objects.get(id=vendor_id)
                if vendor.fsa_establishment_id in mock_fsa_response:
                    data = mock_fsa_response[vendor.fsa_establishment_id]
                    vendor.fsa_rating_value = data['rating_value']
                    vendor.fsa_rating_date = data['rating_date']
                    vendor.fsa_last_checked = timezone.now()
                    vendor.save()
                    return Mock(success=True, data={'rating': data['rating_value']})
                return Mock(success=False, error='Not found')

            mock_update.side_effect = side_effect

            result = bulk_update_fsa_ratings()

        # Should update vendors needing update
        vendor_needs_update.refresh_from_db()
        vendor_never_checked.refresh_from_db()
        vendor_recently_checked.refresh_from_db()

        assert vendor_needs_update.fsa_rating_value == 5  # Updated
        assert vendor_never_checked.fsa_rating_value == 4  # Updated
        assert vendor_recently_checked.fsa_rating_value == 5  # Not updated

        # Check result dictionary with correct keys
        assert result['total'] == 2  # Only 2 needed updates
        assert result['updated'] == 2
        assert result['failed'] == 0

    def test_update_fsa_ratings_with_failures(self):
        """Test handling of failures when updating FSA ratings."""
        vendors = [
            VendorFactory(
                fsa_establishment_id=f'FSA-{i}',
                fsa_last_checked=None
            )
            for i in range(3)
        ]

        with patch('apps.integrations.services.fsa_service.FSAService.update_vendor_rating') as mock_update:
            # First two succeed, third fails
            mock_update.side_effect = [
                Mock(success=True, data={'rating': 5}),
                Mock(success=True, data={'rating': 4}),
                Mock(success=False, error='API error', error_code='API_ERROR')
            ]

            result = bulk_update_fsa_ratings()

        # Check result dictionary with correct keys
        assert result['total'] == 3
        assert result['updated'] == 2
        assert result['failed'] == 1

    def test_update_fsa_ratings_handles_exceptions(self):
        """Test exception handling in FSA update task."""
        VendorFactory(fsa_last_checked=None)

        # Mock the service method that bulk_update_fsa_ratings actually calls
        with patch('apps.integrations.services.fsa_service.FSAService.bulk_update_all_vendors') as mock_bulk:
            # The task catches exceptions and returns stats, doesn't re-raise
            mock_bulk.return_value = {
                'total': 1,
                'updated': 0,
                'failed': 1,
                'skipped': 0
            }

            # Call should succeed and return error stats
            result = bulk_update_fsa_ratings()

            # Verify it handled the error gracefully
            assert result['total'] == 1
            assert result['failed'] == 1
            assert result['updated'] == 0

    def test_update_fsa_ratings_respects_check_frequency(self):
        """Test that recently checked vendors are skipped."""
        # All vendors recently checked (within 7 days)
        vendors = [
            VendorFactory(
                fsa_last_checked=timezone.now() - timedelta(days=i)
            )
            for i in [1, 3, 5]
        ]

        with patch('apps.integrations.services.fsa_service.FSAService.update_vendor_rating') as mock_update:
            result = bulk_update_fsa_ratings()

        # No vendors should be updated
        mock_update.assert_not_called()
        # Check result dictionary with correct key
        assert result['total'] == 0


@pytest.mark.django_db
class TestCheckVendorCompliance:
    """Test vendor compliance checking task."""

    def test_check_compliance_fsa_verification(self):
        """Test checking FSA verification compliance."""
        # Non-compliant: not verified
        vendor_not_verified = VendorFactory(
            is_approved=True,
            fsa_verified=False
        )

        # Non-compliant: low rating
        vendor_low_rating = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=2
        )

        # Non-compliant: stale check
        vendor_stale = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=5,
            fsa_last_checked=timezone.now() - timedelta(days=40)
        )

        # Compliant vendor
        vendor_compliant = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=5,
            fsa_last_checked=timezone.now() - timedelta(days=5)
        )

        result = check_vendor_compliance()

        assert result['checked'] == 4
        assert result['non_compliant'] == 3

        # Check specific issues are identified
        non_compliant_ids = [v['vendor_id'] for v in result['details']]
        assert vendor_not_verified.id in non_compliant_ids
        assert vendor_low_rating.id in non_compliant_ids
        assert vendor_stale.id in non_compliant_ids
        assert vendor_compliant.id not in non_compliant_ids

    def test_check_compliance_stripe_onboarding(self):
        """Test checking Stripe onboarding compliance."""
        vendor_incomplete = VendorFactory(
            is_approved=True,
            stripe_onboarding_complete=False
        )

        vendor_complete = VendorFactory(
            is_approved=True,
            stripe_onboarding_complete=True
        )

        result = check_vendor_compliance()

        assert result['non_compliant'] == 1

        non_compliant = result['details'][0]
        assert non_compliant['vendor_id'] == vendor_incomplete.id
        assert 'Stripe onboarding incomplete' in non_compliant['issues']

    def test_check_compliance_vat_registration(self):
        """Test checking VAT registration for high-volume vendors."""
        # High-volume vendor with empty VAT (use empty string not None)
        vendor_high_volume = VendorFactory(
            is_approved=True,
            vat_number=''  # Empty string, not None
        )

        # Create orders totaling >£7000 in last 30 days
        for _ in range(10):
            OrderFactory(
                vendor=vendor_high_volume,
                status='delivered',
                vendor_payout=Decimal('800.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        # Low-volume vendor without VAT
        vendor_low_volume = VendorFactory(
            is_approved=True,
            vat_number=''  # Empty string, not None
        )

        OrderFactory(
            vendor=vendor_low_volume,
            status='delivered',
            vendor_payout=Decimal('500.00'),
            created_at=timezone.now() - timedelta(days=15)
        )

        result = check_vendor_compliance()

        # Only high-volume vendor should be flagged
        assert result['non_compliant'] == 1

        non_compliant = result['details'][0]
        assert non_compliant['vendor_id'] == vendor_high_volume.id
        assert 'VAT registration required' in non_compliant['issues']

    def test_check_compliance_multiple_issues(self):
        """Test vendor with multiple compliance issues."""
        vendor = VendorFactory(
            is_approved=True,
            fsa_verified=False,
            stripe_onboarding_complete=False,
            vat_number=''  # Empty string, not None
        )

        result = check_vendor_compliance()

        assert result['non_compliant'] == 1

        non_compliant = result['details'][0]
        assert non_compliant['vendor_id'] == vendor.id
        assert len(non_compliant['issues']) == 2
        assert 'FSA not verified' in non_compliant['issues']
        assert 'Stripe onboarding incomplete' in non_compliant['issues']


@pytest.mark.django_db
class TestUpdateVendorCommissionRates:
    """Test vendor commission rate adjustments."""

    def test_reduce_commission_for_high_performers(self):
        """Test commission reduction for high-performing vendors."""
        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.15')  # 15% current rate
        )

        # Create high volume of successful orders (>50k revenue, >100 orders)
        for _ in range(110):
            OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('500.00'),  # Total: 55k
                created_at=timezone.now() - timedelta(days=15)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Should get reduced commission to 8% for top performers
        assert vendor.commission_rate == Decimal('0.08')

        assert result['reviewed'] == 1
        assert result['updated'] == 1

    def test_maintain_existing_rate_for_mid_performers(self):
        """Test that mid-range performers keep existing rate."""
        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.10')  # 10% current rate
        )

        # Create medium volume (5k revenue, 25 orders - between thresholds)
        for _ in range(25):
            OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('200.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Should maintain existing rate (no change for mid performers)
        assert vendor.commission_rate == Decimal('0.10')

        assert result['reviewed'] == 1
        assert result['updated'] == 0  # No change

    def test_increase_commission_for_poor_performance(self):
        """Test commission increase for poor performers."""
        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.10')  # 10% current rate
        )

        # Create low volume (<1k revenue, <10 orders)
        for _ in range(5):
            OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('150.00'),  # Total: 750
                created_at=timezone.now() - timedelta(days=15)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Should get increased commission to 12% for poor performers
        assert vendor.commission_rate == Decimal('0.12')

        assert result['reviewed'] == 1
        assert result['updated'] == 1

    def test_good_performer_gets_9_percent_rate(self):
        """Test commission reduction to 9% for good performers."""
        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.15')  # 15% current rate
        )

        # Create good volume (>20k revenue, >50 orders but <50k/<100)
        for _ in range(60):
            OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('400.00'),  # Total: 24k
                created_at=timezone.now() - timedelta(days=15)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Should get reduced commission to 9% for good performers
        assert vendor.commission_rate == Decimal('0.09')

        assert result['reviewed'] == 1
        assert result['updated'] == 1


@pytest.mark.django_db
class TestCalculateVendorAnalytics:
    """Test vendor analytics calculation task."""

    def test_calculate_daily_analytics(self):
        """Test calculating daily analytics."""
        vendor = VendorFactory(is_approved=True)

        # Create orders for today
        today_order = OrderFactory(
            vendor=vendor,
            status='delivered',
            vendor_payout=Decimal('100.00'),
            created_at=timezone.now()
        )

        # Create order from 2 days ago (should not be included)
        old_order = OrderFactory(
            vendor=vendor,
            status='delivered',
            vendor_payout=Decimal('100.00'),
            created_at=timezone.now() - timedelta(days=2)
        )

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.return_value = Mock(
                success=True,
                data={
                    'revenue': {'total': 100.0, 'orders': 1},
                    'orders': {'total': 1, 'delivered': 1},
                    'top_products': []
                }
            )

            result = calculate_vendor_analytics(vendor.id, period='day')

        assert result['revenue']['total'] == 100.0
        assert result['orders']['total'] == 1

    def test_calculate_weekly_analytics(self):
        """Test calculating weekly analytics."""
        vendor = VendorFactory(is_approved=True)

        # Create orders for the week
        total_orders = 0
        total_revenue = Decimal('0.00')

        for days_ago in range(7):
            order = OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('100.00'),
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            total_orders += 1
            total_revenue += Decimal('100.00')

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.return_value = Mock(
                success=True,
                data={
                    'revenue': {'total': float(total_revenue), 'orders': total_orders},
                    'orders': {'total': total_orders, 'delivered': total_orders},
                    'top_products': []
                }
            )

            result = calculate_vendor_analytics(vendor.id, period='week')

        assert result['revenue']['total'] == float(total_revenue)
        assert result['orders']['total'] == total_orders

    def test_calculate_monthly_analytics(self):
        """Test calculating monthly analytics."""
        vendor = VendorFactory(is_approved=True)

        # Create orders for the month
        now = timezone.now()
        total_orders = 0
        total_revenue = Decimal('0.00')

        for days_ago in range(30):
            order = OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('75.00'),
                created_at=now - timedelta(days=days_ago)
            )
            total_orders += 1
            total_revenue += Decimal('75.00')

        # Add some refunded orders
        for _ in range(3):
            OrderFactory(
                vendor=vendor,
                status='refunded',
                vendor_payout=Decimal('75.00'),
                created_at=now - timedelta(days=10)
            )
            total_orders += 1

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.return_value = Mock(
                success=True,
                data={
                    'revenue': {'total': float(total_revenue)},
                    'orders': {'total': total_orders, 'delivered': 30, 'refunded': 3},
                    'top_products': []
                }
            )

            result = calculate_vendor_analytics(vendor.id, period='month')

        assert result['orders']['total'] == total_orders
        assert result['orders']['delivered'] == 30
        assert result['orders']['refunded'] == 3
        assert result['revenue']['total'] == float(total_revenue)

    def test_calculate_analytics_with_products(self):
        """Test analytics includes product performance data."""
        vendor = VendorFactory(is_approved=True)

        # Create products
        product1 = ProductFactory(vendor=vendor, name='Product 1')
        product2 = ProductFactory(vendor=vendor, name='Product 2')

        # Create orders with items
        now = timezone.now()
        for i in range(10):
            order = OrderFactory(
                vendor=vendor,
                status='delivered',
                created_at=now - timedelta(days=i)
            )

            # Add order items
            from apps.orders.models import OrderItem
            OrderItem.objects.create(
                order=order,
                product=product1 if i < 7 else product2,
                quantity=2,
                unit_price=Decimal('25.00'),
                total_price=Decimal('50.00')
            )

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.return_value = Mock(
                success=True,
                data={
                    'revenue': {'total': 500.0},
                    'orders': {'total': 10},
                    'top_products': [
                        {'product_name': 'Product 1', 'units_sold': 14},
                        {'product_name': 'Product 2', 'units_sold': 6}
                    ]
                }
            )

            result = calculate_vendor_analytics(vendor.id, period='month')

        assert 'top_products' in result
        assert len(result['top_products']) == 2

        # Product 1 should be top (7 orders vs 3)
        assert result['top_products'][0]['product_name'] == 'Product 1'
        assert result['top_products'][0]['units_sold'] == 14

    def test_calculate_analytics_handles_no_data(self):
        """Test analytics calculation when vendor has no orders."""
        vendor = VendorFactory(is_approved=True)

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.return_value = Mock(
                success=True,
                data={
                    'revenue': {'total': 0, 'orders': 0},
                    'orders': {'total': 0},
                    'top_products': []
                }
            )

            result = calculate_vendor_analytics(vendor.id, period='day')

        assert result['revenue']['total'] == 0
        assert result['orders']['total'] == 0
        assert result['top_products'] == []

    def test_calculate_analytics_handles_errors(self):
        """Test error handling in analytics calculation."""
        # Test with non-existent vendor ID - should raise exception
        with pytest.raises(Vendor.DoesNotExist):
            calculate_vendor_analytics(999, period='day')

        # Test with service failure - should raise the exception
        vendor = VendorFactory(is_approved=True)

        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            # Mock a failure response from the service
            mock_report.return_value = Mock(
                success=False,
                error="Database connection failed"
            )

            # The task should raise an exception when service fails
            with pytest.raises(Exception, match="Database connection failed"):
                calculate_vendor_analytics(vendor.id, period='day')
