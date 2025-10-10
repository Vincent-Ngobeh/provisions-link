"""
Celery tasks for product operations.
Handles stock management, price updates, and product analytics.
"""
from celery import shared_task
from django.db.models import F, Q
from django.utils import timezone
from decimal import Decimal
import logging

from django.db import models

logger = logging.getLogger(__name__)


@shared_task(name='check_low_stock_products')
def check_low_stock_products():
    """
    Check for low stock products and notify vendors.
    Runs daily at 9 AM via Celery Beat.
    """
    from apps.products.models import Product
    from apps.vendors.models import Vendor

    try:
        low_stock_by_vendor = {}

        # Find all low stock products
        low_stock = Product.objects.filter(
            is_active=True,
            stock_quantity__lte=F('low_stock_threshold')
        ).select_related('vendor')

        # Group by vendor
        for product in low_stock:
            vendor_id = product.vendor_id
            if vendor_id not in low_stock_by_vendor:
                low_stock_by_vendor[vendor_id] = {
                    'vendor': product.vendor,
                    'products': []
                }

            low_stock_by_vendor[vendor_id]['products'].append({
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'current_stock': product.stock_quantity,
                'threshold': product.low_stock_threshold,
                'is_out_of_stock': product.stock_quantity == 0
            })

        # Send notifications (in production, would send emails)
        for vendor_id, data in low_stock_by_vendor.items():
            vendor = data['vendor']
            products = data['products']
            out_of_stock = [p for p in products if p['is_out_of_stock']]

            logger.warning(
                f"Vendor {vendor.business_name} has {len(products)} low stock items, "
                f"{len(out_of_stock)} out of stock"
            )

            # In production, send email to vendor.user.email
            # For now, just log

        logger.info(
            f"Low stock check complete: {low_stock.count()} products low, "
            f"{len(low_stock_by_vendor)} vendors affected"
        )

        return {
            'total_low_stock': low_stock.count(),
            'vendors_affected': len(low_stock_by_vendor),
            'details': [
                {
                    'vendor_id': vid,
                    'vendor_name': data['vendor'].business_name,
                    'low_stock_count': len(data['products']),
                    'out_of_stock_count': len([p for p in data['products'] if p['is_out_of_stock']])
                }
                for vid, data in low_stock_by_vendor.items()
            ]
        }

    except Exception as e:
        logger.error(f"Error checking low stock: {str(e)}")
        raise


@shared_task(name='update_search_vectors')
def update_search_vectors():
    """
    Update PostgreSQL search vectors for all products.
    Runs weekly to ensure search accuracy.
    """
    from apps.products.models import Product
    from django.contrib.postgres.search import SearchVector

    try:
        updated_count = 0

        # Update in batches to avoid memory issues
        batch_size = 100
        products = Product.objects.all()

        for i in range(0, products.count(), batch_size):
            batch = products[i:i+batch_size]

            for product in batch:
                search_vector = (
                    SearchVector('name', weight='A') +
                    SearchVector('description', weight='B') +
                    SearchVector('sku', weight='C')
                )

                Product.objects.filter(id=product.id).update(
                    search_vector=search_vector
                )
                updated_count += 1

        logger.info(f"Updated search vectors for {updated_count} products")

        return {'updated': updated_count}

    except Exception as e:
        logger.error(f"Error updating search vectors: {str(e)}")
        raise


@shared_task(name='sync_product_stock')
def sync_product_stock(vendor_id=None):
    """
    Sync product stock levels with external systems.
    Can be called for specific vendor or all vendors.

    Args:
        vendor_id: Optional vendor ID to sync
    """
    from apps.products.models import Product

    try:
        if vendor_id:
            products = Product.objects.filter(
                vendor_id=vendor_id, is_active=True)
        else:
            products = Product.objects.filter(is_active=True)

        synced = 0
        errors = []

        for product in products:
            # In production, this would integrate with vendor's inventory system
            # For now, just check for negative stock (data integrity)
            if product.stock_quantity < 0:
                product.stock_quantity = 0
                product.save(update_fields=['stock_quantity'])

                errors.append({
                    'product_id': product.id,
                    'sku': product.sku,
                    'issue': 'Negative stock corrected'
                })

            synced += 1

        logger.info(f"Stock sync complete: {synced} products checked")

        return {
            'synced': synced,
            'errors': len(errors),
            'error_details': errors
        }

    except Exception as e:
        logger.error(f"Error syncing stock: {str(e)}")
        raise


@shared_task(name='calculate_product_analytics')
def calculate_product_analytics():
    """
    Calculate product performance analytics.
    Runs weekly to identify best and worst performers.
    """
    from apps.products.models import Product
    from apps.orders.models import OrderItem
    from datetime import timedelta

    try:
        last_30_days = timezone.now() - timedelta(days=30)

        # Get sales data for last 30 days
        sales_data = OrderItem.objects.filter(
            order__created_at__gte=last_30_days,
            order__status__in=['paid', 'processing', 'shipped', 'delivered']
        ).values('product').annotate(
            units_sold=models.Sum('quantity'),
            revenue=models.Sum('total_price'),
            orders=models.Count('order', distinct=True)
        ).order_by('-revenue')

        # Top 10 best sellers
        best_sellers = list(sales_data[:10])

        # Products with no sales
        products_with_sales = sales_data.values_list('product', flat=True)
        no_sales = Product.objects.filter(
            is_active=True,
            created_at__lte=last_30_days
        ).exclude(id__in=products_with_sales).count()

        logger.info(
            f"Product analytics complete: "
            f"{len(best_sellers)} best sellers, "
            f"{no_sales} products with no sales"
        )

        return {
            'period': 'last_30_days',
            'best_sellers': best_sellers,
            'products_with_no_sales': no_sales,
            'total_products_sold': len(products_with_sales)
        }

    except Exception as e:
        logger.error(f"Error calculating product analytics: {str(e)}")
        raise


@shared_task(name='update_featured_products')
def update_featured_products():
    """
    Automatically update featured products based on performance.
    Runs weekly to keep featured products fresh.
    """
    from apps.products.models import Product
    from apps.orders.models import OrderItem
    from datetime import timedelta

    try:
        # Clear current featured products
        Product.objects.filter(featured=True).update(featured=False)

        # Get top performing products from last 2 weeks
        two_weeks_ago = timezone.now() - timedelta(days=14)

        top_products = OrderItem.objects.filter(
            order__created_at__gte=two_weeks_ago,
            order__status__in=['paid', 'processing', 'shipped', 'delivered']
        ).values('product').annotate(
            score=models.Sum('quantity') * models.Avg('unit_price')
        ).order_by('-score')[:12]  # Top 12 products

        # Mark as featured
        featured_ids = [item['product'] for item in top_products]
        Product.objects.filter(id__in=featured_ids).update(featured=True)

        logger.info(f"Updated {len(featured_ids)} featured products")

        return {
            'featured_count': len(featured_ids),
            'featured_products': featured_ids
        }

    except Exception as e:
        logger.error(f"Error updating featured products: {str(e)}")
        raise


@shared_task(name='cleanup_abandoned_products')
def cleanup_abandoned_products():
    """
    Deactivate products that haven't sold in 6 months.
    Runs monthly to keep catalog fresh.
    """
    from apps.products.models import Product
    from apps.orders.models import OrderItem
    from datetime import timedelta

    try:
        six_months_ago = timezone.now() - timedelta(days=180)

        # Find products with no sales in 6 months
        recent_sales = OrderItem.objects.filter(
            order__created_at__gte=six_months_ago
        ).values_list('product_id', flat=True).distinct()

        # Deactivate products with no recent sales and low stock
        abandoned = Product.objects.filter(
            is_active=True,
            stock_quantity__lt=5,
            created_at__lte=six_months_ago
        ).exclude(id__in=recent_sales)

        deactivated_count = abandoned.update(is_active=False)

        logger.info(f"Deactivated {deactivated_count} abandoned products")

        return {
            'deactivated': deactivated_count,
            'criteria': 'No sales in 6 months and stock < 5'
        }

    except Exception as e:
        logger.error(f"Error cleaning up abandoned products: {str(e)}")
        raise
