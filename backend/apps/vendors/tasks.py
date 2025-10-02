"""
Celery tasks for vendor operations.
Handles FSA updates, vendor analytics, and compliance checks.
"""
from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import logging

from apps.buying_groups import models

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

    Returns:
        Statistics about the update process
    """
    from apps.integrations.services.fsa_service import FSAService

    service = FSAService()

    try:
        logger.info("Starting bulk FSA rating update")

        stats = service.bulk_update_all_vendors()

        logger.info(
            f"Bulk FSA update completed - "
            f"Total: {stats['total']}, "
            f"Updated: {stats['updated']}, "
            f"Failed: {stats['failed']}, "
            f"Skipped: {stats['skipped']}"
        )

        return stats

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
            from apps.orders.models import Order
            from decimal import Decimal

            last_month = timezone.now() - timedelta(days=30)
            monthly_revenue = Order.objects.filter(
                vendor=vendor,
                created_at__gte=last_month,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                total=models.Sum('vendor_payout')
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
    from django.core.cache import cache

    service = VendorService()

    try:
        # Calculate date range
        now = timezone.now()
        if period == 'day':
            date_from = now - timedelta(days=1)
        elif period == 'week':
            date_from = now - timedelta(weeks=1)
        elif period == 'month':
            date_from = now - timedelta(days=30)
        else:
            date_from = now - timedelta(days=365)

        logger.info(f"Calculating {period} analytics for vendor {vendor_id}")

        result = service.get_vendor_performance_report(
            vendor_id=vendor_id,
            date_from=date_from,
            date_to=now
        )

        if result.success:
            # Cache the results
            cache_key = f'vendor_analytics_{vendor_id}_{period}'
            cache.set(cache_key, result.data, timeout=3600)  # 1 hour

            logger.info(f"Calculated analytics for vendor {vendor_id}")
            return result.data
        else:
            logger.error(f"Failed to calculate analytics: {result.error}")
            raise Exception(result.error)

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
            # Calculate last month's performance
            stats = Order.objects.filter(
                vendor=vendor,
                created_at__gte=last_month,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                total_revenue=models.Sum('vendor_payout'),
                order_count=models.Count('id'),
                completion_rate=models.Count(
                    'id',
                    filter=Q(status='delivered')
                ) * 100.0 / models.Count('id')
            )

            revenue = stats['total_revenue'] or Decimal('0')
            orders = stats['order_count'] or 0

            # Adjust commission based on performance
            new_rate = vendor.commission_rate

            if revenue > Decimal('50000') and orders > 100:
                new_rate = Decimal('0.08')  # Reduce to 8% for top performers
            elif revenue > Decimal('20000') and orders > 50:
                new_rate = Decimal('0.09')  # Reduce to 9% for good performers
            elif revenue < Decimal('1000') and orders < 10:
                # Increase to 12% for low performers
                new_rate = Decimal('0.12')

            if new_rate != vendor.commission_rate:
                vendor.commission_rate = new_rate
                vendor.save(update_fields=['commission_rate'])

                updates.append({
                    'vendor_id': vendor.id,
                    'old_rate': float(vendor.commission_rate),
                    'new_rate': float(new_rate),
                    'reason': 'Performance-based adjustment'
                })

                logger.info(
                    f"Updated commission rate for vendor {vendor.id} "
                    f"from {vendor.commission_rate} to {new_rate}"
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
