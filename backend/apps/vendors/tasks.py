"""
Celery tasks for vendor operations.
Handles FSA updates, vendor analytics, and compliance checks.
"""
from celery import shared_task
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from datetime import timedelta, datetime
import logging

from django.db import models

logger = logging.getLogger(__name__)


@shared_task(name='update_vendor_fsa_rating')
def update_vendor_fsa_rating(vendor_id):
    """
    Update a single vendor's FSA rating.
    Called on-demand or when vendor registers.

    Args:
        vendor_id: ID of the vendor to update

    Returns:
        Dict with update results
    """
    from apps.integrations.services.fsa_service import FSAService

    service = FSAService()

    try:
        logger.info(f"Updating FSA rating for vendor {vendor_id}")

        result = service.update_vendor_rating(vendor_id)

        if result.success:
            logger.info(
                f"Updated FSA rating for vendor {vendor_id}: "
                f"Rating {result.data.get('rating')}"
            )
            return {
                'success': True,
                'vendor_id': vendor_id,
                'rating': result.data.get('rating'),
                'rating_date': result.data.get('rating_date')
            }
        else:
            logger.warning(
                f"Failed to update FSA rating for vendor {vendor_id}: "
                f"{result.error}"
            )
            return {
                'success': False,
                'vendor_id': vendor_id,
                'error': result.error
            }

    except Exception as e:
        logger.error(f"Error updating FSA rating: {str(e)}")
        raise


@shared_task(name='bulk_update_fsa_ratings')
def bulk_update_fsa_ratings():
    """
    Bulk update all vendors' FSA ratings.
    Runs weekly via Celery Beat (Monday 2 AM).
    """
    from apps.integrations.services.fsa_service import FSAService
    from apps.vendors.models import Vendor
    from datetime import timedelta

    service = FSAService()

    try:
        logger.info("Starting bulk FSA rating update")

        # Get vendors that need updating (not checked in last 7 days)
        cutoff_date = timezone.now() - timedelta(days=7)
        vendors = Vendor.objects.filter(
            models.Q(fsa_last_checked__isnull=True) |
            models.Q(fsa_last_checked__lt=cutoff_date)
        )

        total = vendors.count()
        updated = 0
        failed = 0
        failures = []

        # Update each vendor and track results
        for vendor in vendors:
            result = service.update_vendor_rating(vendor.id)
            if result.success:
                updated += 1
            else:
                failed += 1
                failures.append({
                    'vendor_id': vendor.id,
                    'error': result.error
                })

        result_dict = {
            'total': total,  # FIXED: Changed from 'total_vendors' to 'total'
            'updated': updated,
            'failed': failed,
            'failures': failures
        }

        logger.info(
            f"Bulk FSA update completed - "
            f"Total: {total}, Updated: {updated}, Failed: {failed}"
        )

        return result_dict

    except Exception as e:
        logger.error(f"Error in bulk FSA update: {str(e)}")
        raise


@shared_task(name='check_vendor_compliance')
def check_vendor_compliance():
    """
    Check vendor compliance status (FSA, Stripe, documents).
    Runs daily to flag non-compliant vendors.
    """
    from apps.vendors.models import Vendor
    from apps.orders.models import Order
    from decimal import Decimal

    try:
        non_compliant = []

        # Check all approved vendors
        vendors = Vendor.objects.filter(is_approved=True)

        for vendor in vendors:
            issues = []

            # Check FSA verification
            if not vendor.fsa_verified:
                issues.append('FSA not verified')
            elif vendor.fsa_rating_value and vendor.fsa_rating_value < 3:
                issues.append(
                    f'FSA rating too low ({vendor.fsa_rating_value})')
            elif vendor.fsa_last_checked:
                days_since_check = (
                    timezone.now() - vendor.fsa_last_checked).days
                if days_since_check > 30:
                    issues.append(
                        f'FSA not checked for {days_since_check} days')

            # Check Stripe onboarding
            if not vendor.stripe_onboarding_complete:
                issues.append('Stripe onboarding incomplete')

            # Check VAT number for high-volume vendors
            last_month = timezone.now() - timedelta(days=30)
            monthly_revenue = Order.objects.filter(
                vendor=vendor,
                created_at__gte=last_month,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                total=Sum('vendor_payout')
            )['total'] or Decimal('0')

            if monthly_revenue > Decimal('7000') and not vendor.vat_number:
                issues.append('VAT registration required')

            if issues:
                non_compliant.append({
                    'vendor_id': vendor.id,
                    'business_name': vendor.business_name,
                    'issues': issues
                })

                logger.warning(
                    f"Vendor {vendor.id} ({vendor.business_name}) "
                    f"compliance issues: {', '.join(issues)}"
                )

        logger.info(
            f"Compliance check complete: {len(non_compliant)} vendors with issues")

        return {
            'checked': vendors.count(),
            'non_compliant': len(non_compliant),
            'details': non_compliant
        }

    except Exception as e:
        logger.error(f"Error checking vendor compliance: {str(e)}")
        raise


@shared_task(name='calculate_vendor_analytics')
def calculate_vendor_analytics(vendor_id, period='week'):
    """
    Calculate and cache vendor analytics.
    Can be called on-demand or scheduled.

    Args:
        vendor_id: Vendor ID
        period: 'day', 'week', 'month', 'year'
    """
    from apps.vendors.services.vendor_service import VendorService
    from apps.vendors.models import Vendor
    from apps.orders.models import Order, OrderItem
    from apps.products.models import Product
    from apps.buying_groups.models import BuyingGroup
    from decimal import Decimal
    from django.core.cache import cache

    try:
        logger.info(f"Calculating {period} analytics for vendor {vendor_id}")

        # Get vendor - this will raise Vendor.DoesNotExist if not found
        vendor = Vendor.objects.get(id=vendor_id)

        # Calculate date range
        now = timezone.now()
        if period == 'day':
            today = now.date()
            date_from = timezone.make_aware(
                datetime.combine(today, datetime.min.time()))
            date_to = timezone.make_aware(
                datetime.combine(today, datetime.max.time()))
        elif period == 'week':
            date_from = now - timedelta(weeks=1)
            date_to = now
        elif period == 'month':
            date_from = now - timedelta(days=30)
            date_to = now
        else:
            date_from = now - timedelta(days=365)
            date_to = now

        # Use the service to get performance report
        service = VendorService()
        result = service.get_vendor_performance_report(
            vendor_id=vendor_id,
            date_from=date_from,
            date_to=date_to
        )

        # FIXED: Check if service call was successful and raise exception if not
        if not result.success:
            raise Exception(result.error)

        # Cache the results
        cache_key = f'vendor_analytics_{vendor_id}_{period}'
        cache.set(cache_key, result.data, timeout=3600)  # 1 hour

        logger.info(f"Calculated analytics for vendor {vendor_id}")
        return result.data

    except Vendor.DoesNotExist:
        logger.error(
            f"Error calculating vendor analytics: Vendor matching query does not exist.")
        raise
    except Exception as e:
        logger.error(f"Error calculating vendor analytics: {str(e)}")
        raise


@shared_task(name='update_vendor_commission_rates')
def update_vendor_commission_rates():
    """
    Review and adjust vendor commission rates based on performance.
    Runs monthly to reward high-performing vendors.
    """
    from apps.vendors.models import Vendor
    from apps.orders.models import Order
    from decimal import Decimal

    try:
        updates = []
        last_month = timezone.now() - timedelta(days=30)

        for vendor in Vendor.objects.filter(is_approved=True):
            # Get all orders in the last month
            all_orders = Order.objects.filter(
                vendor=vendor,
                created_at__gte=last_month
            )

            # Calculate successful orders (paid, processing, shipped, delivered)
            successful_orders = all_orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            )

            # Calculate statistics
            revenue_stats = successful_orders.aggregate(
                total_revenue=Sum('vendor_payout')
            )

            revenue = revenue_stats['total_revenue'] or Decimal('0')
            successful_count = successful_orders.count()

            # Store old rate for tracking
            old_rate = vendor.commission_rate
            new_rate = vendor.commission_rate

            # FIXED: Adjust commission based on performance with correct thresholds
            # Top performers: 100+ orders AND 50k+ revenue → 8%
            if successful_count >= 100 and revenue >= Decimal('50000'):
                new_rate = Decimal('0.08')
            # Good performers: 50+ orders AND 20k+ revenue → 9%
            elif successful_count >= 50 and revenue >= Decimal('20000'):
                new_rate = Decimal('0.09')
            # Poor performers: < 10 orders OR < 1k revenue → 12%
            elif successful_count < 10 or revenue < Decimal('1000'):
                new_rate = Decimal('0.12')
            # Mid-range performers: keep existing rate (no change)
            # This covers vendors between the thresholds

            # Ensure rate stays within bounds (8% min to 20% max)
            new_rate = max(Decimal('0.08'), min(Decimal('0.20'), new_rate))

            if new_rate != old_rate:
                vendor.commission_rate = new_rate
                vendor.save(update_fields=['commission_rate'])

                updates.append({
                    'vendor_id': vendor.id,
                    'old_rate': float(old_rate),
                    'new_rate': float(new_rate),
                    'reason': 'Performance-based adjustment'
                })

                logger.info(
                    f"Updated commission rate for vendor {vendor.id} "
                    f"from {old_rate} to {new_rate}"
                )

        logger.info(f"Commission rate review complete: {len(updates)} updates")

        return {
            'reviewed': Vendor.objects.filter(is_approved=True).count(),
            'updated': len(updates),
            'changes': updates
        }

    except Exception as e:
        logger.error(f"Error updating commission rates: {str(e)}")
        raise
