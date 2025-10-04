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

            with patch('apps.vendors.tasks.logger') as mock_logger:
                result = bulk_update_fsa_ratings()

        # Should update vendors needing update
        vendor_needs_update.refresh_from_db()
        vendor_never_checked.refresh_from_db()
        vendor_recently_checked.refresh_from_db()

        assert vendor_needs_update.fsa_rating_value == 5  # Updated
        assert vendor_never_checked.fsa_rating_value == 4  # Updated
        assert vendor_recently_checked.fsa_rating_value == 5  # Not updated

        assert result['total_vendors'] == 2  # Only 2 needed updates
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

        assert result['total_vendors'] == 3
        assert result['updated'] == 2
        assert result['failed'] == 1
        assert len(result['failures']) == 1
        assert result['failures'][0]['vendor_id'] == vendors[2].id

    def test_update_fsa_ratings_handles_exceptions(self):
        """Test exception handling in FSA update task."""
        VendorFactory(fsa_last_checked=None)

        with patch('apps.integrations.services.fsa_service.FSAService.update_vendor_rating') as mock_update:
            mock_update.side_effect = Exception("API connection failed")

            with patch('apps.vendors.tasks.logger') as mock_logger:
                with pytest.raises(Exception):
                    bulk_update_fsa_ratings()

                mock_logger.error.assert_called()

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
        assert result['total_vendors'] == 0


@pytest.mark.django_db
class TestCheckVendorCompliance:
    """Test vendor compliance checking task."""

    def test_check_compliance_fsa_verification(self):
        """Test checking FSA verification compliance."""
        # Non-compliant: Not FSA verified
        vendor_not_verified = VendorFactory(
            is_approved=True,
            fsa_verified=False,
            business_name='Unverified Vendor'
        )

        # Non-compliant: Low FSA rating
        vendor_low_rating = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=2,
            business_name='Low Rating Vendor'
        )

        # Non-compliant: FSA not checked recently
        vendor_stale_check = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=5,
            fsa_last_checked=timezone.now() - timedelta(days=35),
            business_name='Stale Check Vendor'
        )

        # Compliant vendor
        vendor_compliant = VendorFactory(
            is_approved=True,
            fsa_verified=True,
            fsa_rating_value=4,
            fsa_last_checked=timezone.now() - timedelta(days=5)
        )

        with patch('apps.vendors.tasks.logger') as mock_logger:
            result = check_vendor_compliance()

        assert result['checked'] == 4
        assert result['non_compliant'] == 3

        # Check specific issues identified
        non_compliant_ids = [v['vendor_id'] for v in result['details']]
        assert vendor_not_verified.id in non_compliant_ids
        assert vendor_low_rating.id in non_compliant_ids
        assert vendor_stale_check.id in non_compliant_ids
        assert vendor_compliant.id not in non_compliant_ids

        # Verify correct issues reported
        for vendor_detail in result['details']:
            if vendor_detail['vendor_id'] == vendor_not_verified.id:
                assert 'FSA not verified' in vendor_detail['issues']
            elif vendor_detail['vendor_id'] == vendor_low_rating.id:
                assert 'FSA rating too low (2)' in vendor_detail['issues']
            elif vendor_detail['vendor_id'] == vendor_stale_check.id:
                assert 'FSA not checked for' in ' '.join(
                    vendor_detail['issues'])

    def test_check_compliance_stripe_onboarding(self):
        """Test checking Stripe onboarding compliance."""
        vendor_no_stripe = VendorFactory(
            is_approved=True,
            stripe_onboarding_complete=False,
            business_name='No Stripe Vendor'
        )

        vendor_stripe_complete = VendorFactory(
            is_approved=True,
            stripe_onboarding_complete=True,
            stripe_account_id='acct_test123'
        )

        result = check_vendor_compliance()

        assert result['non_compliant'] == 1
        assert result['details'][0]['vendor_id'] == vendor_no_stripe.id
        assert 'Stripe onboarding incomplete' in result['details'][0]['issues']

    def test_check_compliance_vat_registration(self):
        """Test VAT registration requirement for high-volume vendors."""
        # Create reusable buyer
        buyer = UserFactory()

        # Create high-revenue vendor without VAT number
        vendor_high_revenue = VendorFactory(
            is_approved=True,
            vat_number='',
            business_name='High Revenue Vendor'
        )

        # Create orders to simulate high revenue
        for _ in range(10):
            OrderFactory(
                vendor=vendor_high_revenue,
                buyer=buyer,
                status='delivered',
                vendor_payout=Decimal('1000.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        # Create low-revenue vendor without VAT (compliant)
        vendor_low_revenue = VendorFactory(
            is_approved=True,
            vat_number='',
            business_name='Low Revenue Vendor'
        )

        OrderFactory(
            vendor=vendor_low_revenue,
            buyer=buyer,
            status='delivered',
            vendor_payout=Decimal('500.00'),
            created_at=timezone.now() - timedelta(days=15)
        )

        result = check_vendor_compliance()

        # High revenue vendor should be non-compliant
        non_compliant_ids = [v['vendor_id'] for v in result['details']]
        assert vendor_high_revenue.id in non_compliant_ids

        # Find the high revenue vendor's issues
        for vendor_detail in result['details']:
            if vendor_detail['vendor_id'] == vendor_high_revenue.id:
                assert 'VAT registration required' in vendor_detail['issues']
                break

    def test_check_compliance_multiple_issues(self):
        """Test vendor with multiple compliance issues."""
        # Create reusable buyer
        buyer = UserFactory()

        vendor = VendorFactory(
            is_approved=True,
            fsa_verified=False,
            stripe_onboarding_complete=False,
            vat_number='',
            business_name='Multiple Issues Vendor'
        )

        # Add high revenue
        for _ in range(10):
            OrderFactory(
                vendor=vendor,
                buyer=buyer,
                status='delivered',
                vendor_payout=Decimal('1000.00'),
                created_at=timezone.now() - timedelta(days=10)
            )

        result = check_vendor_compliance()

        # Find this vendor's issues
        vendor_issues = None
        for detail in result['details']:
            if detail['vendor_id'] == vendor.id:
                vendor_issues = detail['issues']
                break

        assert vendor_issues is not None
        assert len(vendor_issues) >= 3
        assert 'FSA not verified' in vendor_issues
        assert 'Stripe onboarding incomplete' in vendor_issues
        assert 'VAT registration required' in vendor_issues


@pytest.mark.django_db
class TestUpdateVendorCommissionRates:
    """Test commission rate adjustment based on performance."""

    def test_reduce_commission_for_high_performers(self):
        """Test commission reduction for vendors with excellent performance."""
        # Create buyers to reuse
        buyer1 = UserFactory()
        buyer2 = UserFactory()

        # High-performing vendor
        vendor_high = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.15'),  # 15% current rate
            business_name='High Performer'
        )

        # Create successful orders
        for i in range(50):
            OrderFactory(
                vendor=vendor_high,
                buyer=buyer1 if i % 2 == 0 else buyer2,
                status='delivered',
                total=Decimal('100.00'),
                vendor_payout=Decimal('85.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        # Low-performing vendor
        vendor_low = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.15'),
            business_name='Low Performer'
        )

        # Create fewer orders with some cancellations
        for i in range(10):
            OrderFactory(
                vendor=vendor_low,
                buyer=buyer1 if i % 2 == 0 else buyer2,
                status='cancelled' if i < 3 else 'delivered',
                total=Decimal('100.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        with patch('apps.vendors.tasks.logger') as mock_logger:
            result = update_vendor_commission_rates()

        vendor_high.refresh_from_db()
        vendor_low.refresh_from_db()

        # High performer should get reduced commission
        assert vendor_high.commission_rate < Decimal('0.15')
        # Low performer should maintain or increase commission
        assert vendor_low.commission_rate >= Decimal('0.15')

        assert result['reviewed'] == 2
        assert result['adjusted'] == 1

    def test_maintain_minimum_commission_rate(self):
        """Test that commission never goes below minimum threshold."""
        # Create buyers to reuse
        buyer1 = UserFactory()
        buyer2 = UserFactory()
        buyer3 = UserFactory()

        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.08'),  # Already at low rate
            business_name='Excellent Vendor'
        )

        # Create many successful orders
        for i in range(100):
            OrderFactory(
                vendor=vendor,
                buyer=buyer1 if i % 3 == 0 else (
                    buyer2 if i % 3 == 1 else buyer3),
                status='delivered',
                total=Decimal('100.00'),
                created_at=timezone.now() - timedelta(days=10)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Should not go below minimum (assuming 7% minimum)
        assert vendor.commission_rate >= Decimal('0.07')

    def test_increase_commission_for_poor_performance(self):
        """Test commission increase for vendors with poor fulfillment."""
        # Create buyers to reuse
        buyer1 = UserFactory()
        buyer2 = UserFactory()

        vendor = VendorFactory(
            is_approved=True,
            commission_rate=Decimal('0.10'),
            business_name='Poor Performer'
        )

        # Create orders with high cancellation rate
        for i in range(20):
            OrderFactory(
                vendor=vendor,
                buyer=buyer1 if i % 2 == 0 else buyer2,
                status='cancelled' if i < 10 else 'delivered',
                total=Decimal('100.00'),
                created_at=timezone.now() - timedelta(days=15)
            )

        result = update_vendor_commission_rates()

        vendor.refresh_from_db()
        # Commission should increase due to poor performance
        assert vendor.commission_rate > Decimal('0.10')
        # But not exceed maximum (assuming 20% maximum)
        assert vendor.commission_rate <= Decimal('0.20')


@pytest.mark.django_db
class TestCalculateVendorAnalytics:
    """Test vendor analytics calculation task."""

    def test_calculate_daily_analytics(self):
        """Test calculating daily analytics for a vendor."""
        vendor = VendorFactory(is_approved=True)

        # Create today's orders
        today = timezone.now().date()
        today_start = timezone.make_aware(
            datetime.combine(today, datetime.min.time()))

        for i in range(5):
            OrderFactory(
                vendor=vendor,
                status='delivered',
                vendor_payout=Decimal('100.00'),
                created_at=today_start + timedelta(hours=i)
            )

        # Create yesterday's orders (should not be included)
        yesterday = today_start - timedelta(days=1)
        OrderFactory(
            vendor=vendor,
            status='delivered',
            vendor_payout=Decimal('100.00'),
            created_at=yesterday
        )

        with patch('django.core.cache.cache.set') as mock_cache_set:
            result = calculate_vendor_analytics(vendor.id, period='day')

        assert result['revenue']['total'] == 500.0  # 5 * 100
        assert result['orders']['total'] == 5

        # Verify caching
        mock_cache_set.assert_called_once()
        cache_key = mock_cache_set.call_args[0][0]
        assert f'vendor_analytics_{vendor.id}_day' in cache_key

    def test_calculate_weekly_analytics(self):
        """Test calculating weekly analytics for a vendor."""
        vendor = VendorFactory(is_approved=True)

        # Create orders throughout the week
        now = timezone.now()
        for days_ago in range(7):
            for _ in range(2):  # 2 orders per day
                OrderFactory(
                    vendor=vendor,
                    status='delivered',
                    vendor_payout=Decimal('50.00'),
                    created_at=now - timedelta(days=days_ago)
                )

        with patch('django.core.cache.cache.set') as mock_cache_set:
            result = calculate_vendor_analytics(vendor.id, period='week')

        assert result['revenue']['total'] == 700.0  # 7 * 2 * 50
        assert result['orders']['total'] == 14

    def test_calculate_monthly_analytics(self):
        """Test calculating monthly analytics for a vendor."""
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

        result = calculate_vendor_analytics(vendor.id, period='month')

        assert 'top_products' in result
        assert len(result['top_products']) == 2

        # Product 1 should be top (7 orders vs 3)
        assert result['top_products'][0]['product_name'] == 'Product 1'
        # 7 orders * 2 units
        assert result['top_products'][0]['units_sold'] == 14

    def test_calculate_analytics_handles_no_data(self):
        """Test analytics calculation when vendor has no orders."""
        vendor = VendorFactory(is_approved=True)

        result = calculate_vendor_analytics(vendor.id, period='day')

        assert result['revenue']['total'] == 0
        assert result['orders']['total'] == 0
        assert result['top_products'] == []

    def test_calculate_analytics_handles_errors(self):
        """Test error handling in analytics calculation."""
        with patch('apps.vendors.services.vendor_service.VendorService.get_vendor_performance_report') as mock_report:
            mock_report.side_effect = Exception("Database error")

            with patch('apps.vendors.tasks.logger') as mock_logger:
                with pytest.raises(Exception):
                    calculate_vendor_analytics(999, period='day')

                mock_logger.error.assert_called()
