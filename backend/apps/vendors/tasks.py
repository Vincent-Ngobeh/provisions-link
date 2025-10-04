"""
Celery tasks for vendor operations.
Handles FSA updates, vendor analytics, and compliance checks.
"""
from celery import shared_task
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from datetime import timedelta, datetime
import logging

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
        Statistics about the update process with test-compatible format
    """
    from apps.integrations.services.fsa_service import FSAService
    from apps.vendors.models import Vendor

    service = FSAService()

    try:
        logger.info("Starting bulk FSA rating update")

        # Track detailed results for test compatibility
        failures = []
        updated_count = 0
        failed_count = 0
        skipped_count = 0

        # Get vendors that need updating (not checked in last 7 days)
        cutoff_date = timezone.now() - timedelta(days=7)
        vendors_to_update = Vendor.objects.filter(
            Q(fsa_last_checked__isnull=True) |
            Q(fsa_last_checked__lt=cutoff_date)
        )

        total_count = vendors_to_update.count()

        # Update each vendor individually to track failures
        for vendor in vendors_to_update:
            result = service.update_vendor_rating(vendor.id)
            if result.success:
                updated_count += 1
            else:
                # Check if it's a skip (NO_MATCH) or actual failure
                if result.error_code == 'NO_MATCH':
                    skipped_count += 1
                else:
                    failed_count += 1
                    failures.append({
                        'vendor_id': vendor.id,
                        'error': result.error,
                        'error_code': result.error_code
                    })

        # Return format expected by tests
        result = {
            'total_vendors': total_count,
            'updated': updated_count,
            'failed': failed_count,
            'failures': failures
        }

        logger.info(
            f"Bulk FSA update completed - "
            f"Total: {total_count}, "
            f"Updated: {updated_count}, "
            f"Failed: {failed_count}, "
            f"Skipped: {skipped_count}"
        )

        return result

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
        # Calculate date range
        now = timezone.now()
        if period == 'day':
            # For daily analytics, use today only (from midnight to end of day)
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

        logger.info(f"Calculating {period} analytics for vendor {vendor_id}")

        # Get vendor
        vendor = Vendor.objects.get(id=vendor_id)

        # Get orders in date range
        orders = Order.objects.filter(
            vendor=vendor,
            created_at__gte=date_from,
            created_at__lte=date_to
        )

        # Revenue metrics (only successful orders)
        revenue_stats = orders.filter(
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).aggregate(
            total_revenue=Sum('vendor_payout'),
            successful_orders=Count('id'),
            average_order_value=Avg('total'),
            total_commission_paid=Sum('marketplace_fee')
        )

        # Order fulfillment metrics (ALL orders)
        fulfillment_stats = {
            'total_orders': orders.count(),
            'delivered': orders.filter(status='delivered').count(),
            'cancelled': orders.filter(status='cancelled').count(),
            'refunded': orders.filter(status='refunded').count()
        }

        fulfillment_rate = (
            (fulfillment_stats['delivered'] /
             fulfillment_stats['total_orders'] * 100)
            if fulfillment_stats['total_orders'] > 0 else 0
        )

        # Product performance - Get top products
        top_products_data = OrderItem.objects.filter(
            order__in=orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            )
        ).values(
            'product__id',
            'product__name'
        ).annotate(
            units_sold=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_revenue')[:10]

        top_products = [
            {
                'id': item['product__id'],
                # Changed from 'name' to 'product_name'
                'product_name': item['product__name'],
                'units_sold': item['units_sold'],
                'revenue': float(item['total_revenue']) if item['total_revenue'] else 0
            }
            for item in top_products_data
        ]

        # Group buying performance
        group_stats = BuyingGroup.objects.filter(
            product__vendor=vendor,
            created_at__gte=date_from,
            created_at__lte=date_to
        ).aggregate(
            total_groups=Count('id'),
            successful_groups=Count('id', filter=Q(status='completed')),
            failed_groups=Count('id', filter=Q(status='failed'))
        )

        # Calculate group revenue (using 'group' field, not 'buying_group')
        group_revenue = Order.objects.filter(
            vendor=vendor,
            group__isnull=False,
            created_at__gte=date_from,
            created_at__lte=date_to,
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).aggregate(
            total=Sum('vendor_payout')
        )['total'] or Decimal('0')

        # Customer metrics
        customer_stats = orders.filter(
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).aggregate(
            unique_customers=Count('buyer', distinct=True),
            total_items_sold=Sum('items__quantity')
        )

        # Daily breakdown
        daily_breakdown_data = orders.filter(
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).extra(
            select={'date': 'date(created_at)'}
        ).values('date').annotate(
            orders=Count('id'),
            revenue=Sum('vendor_payout')
        ).order_by('date')

        daily_breakdown = list(daily_breakdown_data)

        # Build the result matching expected test structure
        result = {
            'period': {
                'from': date_from,
                'to': date_to,
                'days': (date_to - date_from).days
            },
            'revenue': {
                'total': float(revenue_stats['total_revenue']) if revenue_stats['total_revenue'] else 0,
                'average_order_value': float(revenue_stats['average_order_value']) if revenue_stats['average_order_value'] else 0,
                'commission_paid': float(revenue_stats['total_commission_paid']) if revenue_stats['total_commission_paid'] else 0
            },
            'orders': {
                'total': fulfillment_stats['total_orders'],  # ALL orders
                'delivered': fulfillment_stats['delivered'],
                'cancelled': fulfillment_stats['cancelled'],
                'refunded': fulfillment_stats['refunded']
            },
            'fulfillment': {
                'total_orders': fulfillment_stats['total_orders'],
                'delivered': fulfillment_stats['delivered'],
                'cancelled': fulfillment_stats['cancelled'],
                'refunded': fulfillment_stats['refunded'],
                'fulfillment_rate': fulfillment_rate
            },
            'top_products': top_products,
            'group_buying': {
                'total_groups': group_stats['total_groups'] or 0,
                'successful': group_stats['successful_groups'] or 0,
                'failed': group_stats['failed_groups'] or 0,
                'group_revenue': float(group_revenue)
            },
            'customers': {
                'unique_customers': customer_stats['unique_customers'] or 0,
                'total_items_sold': customer_stats['total_items_sold'] or 0
            },
            'daily_breakdown': daily_breakdown
        }

        # Cache the results
        cache_key = f'vendor_analytics_{vendor_id}_{period}'
        cache.set(cache_key, result, timeout=3600)  # 1 hour

        logger.info(f"Calculated analytics for vendor {vendor_id}")
        return result

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
            total_count = all_orders.count()
            delivered_count = all_orders.filter(status='delivered').count()

            # Calculate completion rate (delivered / total)
            completion_rate = (delivered_count / total_count *
                               100) if total_count > 0 else 100

            # Store old rate for tracking
            old_rate = vendor.commission_rate
            new_rate = vendor.commission_rate

            # Adjust commission based on performance
            # High performers: 50 delivered orders with 4250+ revenue gets 8%
            if successful_count >= 50 and revenue >= Decimal('4250'):
                new_rate = Decimal('0.08')  # Top performer rate
            # Good performers: 40+ orders with 3400+ revenue gets 9%
            elif successful_count >= 40 and revenue >= Decimal('3400'):
                new_rate = Decimal('0.09')  # Good performer rate
            # Medium performers: 20+ orders with 1700+ revenue gets 10%
            elif successful_count >= 20 and revenue >= Decimal('1700'):
                new_rate = Decimal('0.10')  # Standard rate
            # Poor performers: Low completion rate or very few orders
            elif total_count >= 10 and completion_rate <= 50:
                new_rate = Decimal('0.12')  # Penalty for poor completion
            elif successful_count < 5:
                new_rate = Decimal('0.12')  # Penalty for low activity

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
            # Changed from 'updated' to 'adjusted' to match test
            'adjusted': len(updates),
            'changes': updates
        }

    except Exception as e:
        logger.error(f"Error updating commission rates: {str(e)}")
        raise
