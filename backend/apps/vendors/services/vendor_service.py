"""
Vendor service for managing vendor operations.
Handles vendor onboarding, verification, analytics, and vendor-specific business logic.
"""
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F, Q, Sum, Count, Avg, Prefetch
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D

from apps.core.services.base import (
    BaseService, ServiceResult, ValidationError,
    BusinessRuleViolation
)
from apps.vendors.models import Vendor
from apps.products.models import Product
from apps.orders.models import Order, OrderItem
from apps.buying_groups.models import BuyingGroup
from apps.core.models import User
from apps.integrations.services.fsa_service import FSAService


class VendorService(BaseService):
    """
    Service for managing vendor operations and business logic.
    """

    # Business rule constants
    MIN_DELIVERY_RADIUS_KM = 1
    MAX_DELIVERY_RADIUS_KM = 50
    MIN_COMMISSION_RATE = Decimal('0.05')  # 5%
    MAX_COMMISSION_RATE = Decimal('0.30')  # 30%
    DEFAULT_COMMISSION_RATE = Decimal('0.10')  # 10%

    # Vendor approval thresholds
    MIN_FSA_RATING_FOR_APPROVAL = 3
    DAYS_BEFORE_RATING_STALE = 365

    @transaction.atomic
    def register_vendor(
        self,
        user: User,
        business_name: str,
        description: str,
        postcode: str,
        delivery_radius_km: int,
        min_order_value: Decimal,
        phone_number: Optional[str] = None,
        vat_number: Optional[str] = None
    ) -> ServiceResult:
        """
        Register a new vendor account.

        Args:
            user: User creating the vendor account
            business_name: Legal business name
            description: Business description
            postcode: Business postcode
            delivery_radius_km: Delivery radius in kilometers
            min_order_value: Minimum order value
            phone_number: Optional business phone
            vat_number: Optional VAT registration number

        Returns:
            ServiceResult containing created Vendor or error
        """
        try:
            # Check if user already has a vendor account
            if hasattr(user, 'vendor'):
                return ServiceResult.fail(
                    "User already has a vendor account",
                    error_code="VENDOR_EXISTS"
                )

            # Validate business name uniqueness
            if Vendor.objects.filter(business_name__iexact=business_name).exists():
                return ServiceResult.fail(
                    "Business name already registered",
                    error_code="BUSINESS_NAME_EXISTS"
                )

            # Validate delivery radius
            if not self.MIN_DELIVERY_RADIUS_KM <= delivery_radius_km <= self.MAX_DELIVERY_RADIUS_KM:
                return ServiceResult.fail(
                    f"Delivery radius must be between {self.MIN_DELIVERY_RADIUS_KM} and {self.MAX_DELIVERY_RADIUS_KM} km",
                    error_code="INVALID_RADIUS"
                )

            # Validate minimum order value
            if min_order_value < Decimal('0.00'):
                return ServiceResult.fail(
                    "Minimum order value must be positive",
                    error_code="INVALID_MIN_ORDER"
                )

            # Geocode postcode
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()

            location_result = geo_service.geocode_postcode(postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Could not verify postcode: {location_result.error}",
                    error_code="INVALID_POSTCODE"
                )

            location = location_result.data['point']

            # Create vendor account
            vendor = Vendor.objects.create(
                user=user,
                business_name=business_name,
                description=description,
                phone_number=phone_number or '',
                location=location,
                postcode=postcode.upper(),
                delivery_radius_km=delivery_radius_km,
                min_order_value=min_order_value,
                vat_number=vat_number or '',
                commission_rate=self.DEFAULT_COMMISSION_RATE,
                is_approved=False,  # Requires admin approval
                fsa_verified=False,  # Requires FSA check
                stripe_onboarding_complete=False  # Requires Stripe onboarding
            )

            # Trigger FSA verification
            fsa_result = self._initiate_fsa_verification(vendor)

            if fsa_result.success:
                vendor.fsa_establishment_id = fsa_result.data.get('fsa_id')
                vendor.fsa_rating_value = fsa_result.data.get('rating')
                vendor.fsa_rating_date = fsa_result.data.get('rating_date')
                vendor.fsa_verified = True
                vendor.fsa_last_checked = timezone.now()
                vendor.save(update_fields=[
                    'fsa_establishment_id',
                    'fsa_rating_value',
                    'fsa_rating_date',
                    'fsa_verified',
                    'fsa_last_checked'
                ])

            # Create Stripe Connect account
            from apps.integrations.services.stripe_service import StripeConnectService
            stripe_service = StripeConnectService()

            stripe_result = stripe_service.create_vendor_account(vendor)

            onboarding_url = None
            if stripe_result.success:
                vendor.stripe_account_id = stripe_result.data.get('account_id')
                vendor.save(update_fields=['stripe_account_id'])
                onboarding_url = stripe_result.data.get('onboarding_url')

            self.log_info(
                f"Registered vendor {vendor.business_name}",
                vendor_id=vendor.id,
                user_id=user.id
            )

            return ServiceResult.ok({
                'vendor': vendor,
                'onboarding_url': onboarding_url,
                'fsa_verified': vendor.fsa_verified,
                'needs_approval': True
            })

        except Exception as e:
            self.log_error(
                f"Error registering vendor",
                exception=e,
                user_id=user.id,
                business_name=business_name
            )
            return ServiceResult.fail(
                "Failed to register vendor",
                error_code="REGISTRATION_FAILED"
            )

    def update_vendor_profile(
        self,
        vendor_id: int,
        user: User,
        **update_fields
    ) -> ServiceResult:
        """
        Update vendor profile information.

        Args:
            vendor_id: Vendor ID
            user: User making the update
            **update_fields: Fields to update

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            vendor = Vendor.objects.get(id=vendor_id)

            # Check permission
            if vendor.user != user and not user.is_staff:
                return ServiceResult.fail(
                    "Permission denied",
                    error_code="PERMISSION_DENIED"
                )

            # Allowed fields for update
            allowed_fields = [
                'description', 'phone_number', 'delivery_radius_km',
                'min_order_value'
            ]

            # Filter and validate update fields
            updates = {}

            for field, value in update_fields.items():
                if field not in allowed_fields:
                    continue

                # Validate specific fields
                if field == 'delivery_radius_km':
                    if not self.MIN_DELIVERY_RADIUS_KM <= value <= self.MAX_DELIVERY_RADIUS_KM:
                        return ServiceResult.fail(
                            f"Invalid delivery radius",
                            error_code="INVALID_RADIUS"
                        )

                elif field == 'min_order_value':
                    if value < Decimal('0.00'):
                        return ServiceResult.fail(
                            "Minimum order value must be positive",
                            error_code="INVALID_MIN_ORDER"
                        )

                updates[field] = value

            # Apply updates
            for field, value in updates.items():
                setattr(vendor, field, value)

            vendor.save(update_fields=list(updates.keys()))

            self.log_info(
                f"Updated vendor profile",
                vendor_id=vendor_id,
                updated_fields=list(updates.keys())
            )

            return ServiceResult.ok({
                'vendor': vendor,
                'updated_fields': list(updates.keys())
            })

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error updating vendor profile",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to update vendor profile",
                error_code="UPDATE_FAILED"
            )

    def approve_vendor(
        self,
        vendor_id: int,
        admin_user: User,
        commission_rate: Optional[Decimal] = None
    ) -> ServiceResult:
        """
        Approve a vendor for marketplace selling (admin only).

        Args:
            vendor_id: Vendor ID
            admin_user: Admin user approving the vendor
            commission_rate: Optional custom commission rate

        Returns:
            ServiceResult indicating success or failure
        """
        try:
            if not admin_user.is_staff:
                return ServiceResult.fail(
                    "Only staff can approve vendors",
                    error_code="PERMISSION_DENIED"
                )

            vendor = Vendor.objects.get(id=vendor_id)

            # Check if already approved
            if vendor.is_approved:
                return ServiceResult.fail(
                    "Vendor already approved",
                    error_code="ALREADY_APPROVED"
                )

            # Validate FSA rating if verified
            if vendor.fsa_verified and vendor.fsa_rating_value:
                if vendor.fsa_rating_value < self.MIN_FSA_RATING_FOR_APPROVAL:
                    return ServiceResult.fail(
                        f"FSA rating too low (minimum {self.MIN_FSA_RATING_FOR_APPROVAL} required)",
                        error_code="FSA_RATING_TOO_LOW"
                    )

            # Set commission rate
            if commission_rate is not None:
                if not self.MIN_COMMISSION_RATE <= commission_rate <= self.MAX_COMMISSION_RATE:
                    return ServiceResult.fail(
                        f"Commission rate must be between {self.MIN_COMMISSION_RATE*100}% and {self.MAX_COMMISSION_RATE*100}%",
                        error_code="INVALID_COMMISSION"
                    )
                vendor.commission_rate = commission_rate

            # Approve vendor
            vendor.is_approved = True
            vendor.save(update_fields=['is_approved', 'commission_rate'])

            self.log_info(
                f"Vendor approved",
                vendor_id=vendor_id,
                admin_id=admin_user.id,
                commission_rate=float(vendor.commission_rate)
            )

            return ServiceResult.ok({
                'vendor': vendor,
                'message': 'Vendor approved successfully'
            })

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error approving vendor",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to approve vendor",
                error_code="APPROVAL_FAILED"
            )

    def get_vendor_dashboard_metrics(self, vendor_id: int) -> ServiceResult:
        """
        Get dashboard metrics for a vendor.

        Args:
            vendor_id: Vendor ID

        Returns:
            ServiceResult containing dashboard metrics
        """
        try:
            vendor = Vendor.objects.get(id=vendor_id)

            # Today's metrics
            today = timezone.now().date()
            today_start = timezone.make_aware(
                datetime.combine(today, datetime.min.time())
            )

            today_orders = Order.objects.filter(
                vendor=vendor,
                created_at__gte=today_start
            )

            today_revenue = today_orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                total=Sum('vendor_payout')
            )['total'] or Decimal('0.00')

            # This week's metrics
            week_start = today_start - timedelta(days=today.weekday())

            week_orders = Order.objects.filter(
                vendor=vendor,
                created_at__gte=week_start,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            )

            week_revenue = week_orders.aggregate(
                total=Sum('vendor_payout')
            )['total'] or Decimal('0.00')

            # Pending orders
            pending_orders = Order.objects.filter(
                vendor=vendor,
                status__in=['paid', 'processing']
            ).count()

            # Low stock products
            low_stock_products = Product.objects.filter(
                vendor=vendor,
                is_active=True,
                stock_quantity__lte=F('low_stock_threshold')
            ).count()

            # Out of stock products
            out_of_stock = Product.objects.filter(
                vendor=vendor,
                is_active=True,
                stock_quantity=0
            ).count()

            # Active buying groups
            active_groups = BuyingGroup.objects.filter(
                product__vendor=vendor,
                status='open'
            ).count()

            # Top products (last 30 days)
            thirty_days_ago = timezone.now() - timedelta(days=30)

            top_products = OrderItem.objects.filter(
                order__vendor=vendor,
                order__created_at__gte=thirty_days_ago,
                order__status__in=[
                    'paid', 'processing', 'shipped', 'delivered']
            ).values(
                'product__id',
                'product__name'
            ).annotate(
                quantity_sold=Sum('quantity'),
                revenue=Sum('total_price')
            ).order_by('-revenue')[:5]

            # Recent orders
            recent_orders = Order.objects.filter(
                vendor=vendor
            ).select_related('buyer').order_by('-created_at')[:10]

            recent_orders_data = [
                {
                    'id': order.id,
                    'reference': order.reference_number,
                    'buyer': order.buyer.get_full_name() or order.buyer.email,
                    'total': float(order.total),
                    'status': order.status,
                    'created_at': order.created_at
                }
                for order in recent_orders
            ]

            # Customer metrics
            unique_customers = Order.objects.filter(
                vendor=vendor,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).values('buyer').distinct().count()

            repeat_customers = Order.objects.filter(
                vendor=vendor,
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).values('buyer').annotate(
                order_count=Count('id')
            ).filter(order_count__gt=1).count()

            return ServiceResult.ok({
                'summary': {
                    'today_revenue': float(today_revenue),
                    'today_orders': today_orders.count(),
                    'week_revenue': float(week_revenue),
                    'week_orders': week_orders.count(),
                    'pending_orders': pending_orders,
                    'low_stock_products': low_stock_products,
                    'out_of_stock': out_of_stock,
                    'active_groups': active_groups
                },
                'top_products': list(top_products),
                'recent_orders': recent_orders_data,
                'customers': {
                    'total': unique_customers,
                    'repeat': repeat_customers,
                    'repeat_rate': round((repeat_customers / unique_customers * 100) if unique_customers > 0 else 0, 1)
                },
                'vendor_status': {
                    'is_approved': vendor.is_approved,
                    'fsa_verified': vendor.fsa_verified,
                    'fsa_rating': vendor.fsa_rating_value,
                    'stripe_ready': vendor.stripe_onboarding_complete,
                    'commission_rate': float(vendor.commission_rate * 100)
                }
            })

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error getting vendor dashboard metrics",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to get dashboard metrics",
                error_code="METRICS_FAILED"
            )

    def search_vendors_by_location(
        self,
        postcode: str,
        radius_km: Optional[int] = 10,
        min_rating: Optional[int] = None,
        only_verified: bool = False,
        category_id: Optional[int] = None
    ) -> ServiceResult:
        """
        Search for vendors delivering to a location.

        Args:
            postcode: Delivery postcode
            radius_km: Search radius
            min_rating: Minimum FSA rating
            only_verified: Only show FSA verified vendors
            category_id: Filter by product category

        Returns:
            ServiceResult containing list of vendors
        """
        try:
            # Geocode postcode
            from apps.integrations.services.geocoding_service import GeocodingService
            geo_service = GeocodingService()

            location_result = geo_service.geocode_postcode(postcode)

            if not location_result.success:
                return ServiceResult.fail(
                    f"Invalid postcode: {location_result.error}",
                    error_code="INVALID_POSTCODE"
                )

            delivery_point = location_result.data['point']

            # Find vendors that can deliver to this location
            vendors = Vendor.objects.filter(
                is_approved=True,
                location__distance_lte=(delivery_point, D(km=radius_km))
            )

            # Additional filters
            if min_rating:
                vendors = vendors.filter(fsa_rating_value__gte=min_rating)

            if only_verified:
                vendors = vendors.filter(fsa_verified=True)

            if category_id:
                vendors = vendors.filter(
                    products__category_id=category_id,
                    products__is_active=True
                ).distinct()

            # Annotate with distance
            vendors = vendors.annotate(
                distance_km=Distance('location', delivery_point)
            ).order_by('distance_km')

            # Check if each vendor actually delivers to this location
            results = []
            for vendor in vendors[:20]:  # Limit to 20 results
                # Check if delivery point is within vendor's delivery radius
                vendor_distance = geo_service.calculate_distance(
                    vendor.location,
                    delivery_point
                )

                if vendor_distance <= vendor.delivery_radius_km:
                    # Safely get logo URL
                    logo_url = None
                    if vendor.logo and vendor.logo.name not in ('', None):
                        try:
                            logo_url = vendor.logo.url
                        except (ValueError, AttributeError):
                            pass

                    results.append({
                        'id': vendor.id,
                        'business_name': vendor.business_name,
                        'slug': vendor.slug,
                        'description': vendor.description[:200],
                        'postcode': vendor.postcode,
                        'fsa_rating_value': vendor.fsa_rating_value,
                        'fsa_rating_display': vendor.fsa_rating_display,
                        'min_order_value': float(vendor.min_order_value),
                        'delivery_radius_km': vendor.delivery_radius_km,
                        'distance_km': float(vendor_distance),
                        'logo_url': logo_url,
                        'product_count': vendor.products.filter(is_active=True).count(),
                        'is_approved': vendor.is_approved,
                        'stripe_onboarding_complete': vendor.stripe_onboarding_complete,
                    })

            return ServiceResult.ok({
                'vendors': results,
                'count': len(results),
                'search_location': postcode,
                'search_radius_km': radius_km
            })

        except Exception as e:
            self.log_error(
                f"Error searching vendors by location",
                exception=e,
                postcode=postcode
            )
            return ServiceResult.fail(
                "Failed to search vendors",
                error_code="SEARCH_FAILED"
            )

    def get_vendor_performance_report(
        self,
        vendor_id: int,
        date_from: datetime,
        date_to: datetime
    ) -> ServiceResult:
        """
        Generate performance report for a vendor.

        Args:
            vendor_id: Vendor ID
            date_from: Report start date
            date_to: Report end date

        Returns:
            ServiceResult containing performance metrics
        """
        try:
            vendor = Vendor.objects.get(id=vendor_id)

            # Get orders in date range
            orders = Order.objects.filter(
                vendor=vendor,
                created_at__gte=date_from,
                created_at__lte=date_to
            )

            # Revenue metrics
            revenue_stats = orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                total_revenue=Sum('vendor_payout'),
                total_orders=Count('id'),
                average_order_value=Avg('total'),
                total_commission_paid=Sum('marketplace_fee')
            )

            # Order fulfillment metrics
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

            # Product performance
            product_performance = OrderItem.objects.filter(
                order__in=orders,
                order__status__in=[
                    'paid', 'processing', 'shipped', 'delivered']
            ).values(
                'product__id',
                'product__name',
                'product__sku'
            ).annotate(
                units_sold=Sum('quantity'),
                total_revenue=Sum('total_price')
            ).order_by('-total_revenue')[:10]

            # Group buying performance
            group_stats = BuyingGroup.objects.filter(
                product__vendor=vendor,
                created_at__gte=date_from,
                created_at__lte=date_to
            ).aggregate(
                total_groups=Count('id'),
                successful_groups=Count('id', filter=Q(status='completed')),
                failed_groups=Count('id', filter=Q(status='failed')),
                total_group_revenue=Sum(
                    'orders__total',
                    filter=Q(orders__status__in=[
                             'paid', 'processing', 'shipped', 'delivered'])
                )
            )

            # Customer metrics
            customer_stats = orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).aggregate(
                unique_customers=Count('buyer', distinct=True),
                total_items_sold=Sum('items__quantity')
            )

            # Daily breakdown
            daily_breakdown = orders.filter(
                status__in=['paid', 'processing', 'shipped', 'delivered']
            ).extra(
                select={'date': 'date(created_at)'}
            ).values('date').annotate(
                orders=Count('id'),
                revenue=Sum('vendor_payout')
            ).order_by('date')

            return ServiceResult.ok({
                'period': {
                    'from': date_from,
                    'to': date_to,
                    'days': (date_to - date_from).days
                },
                'revenue': {
                    'total': float(revenue_stats['total_revenue'] or 0),
                    'orders': revenue_stats['total_orders'] or 0,
                    'average_order': float(revenue_stats['average_order_value'] or 0),
                    'commission_paid': float(revenue_stats['total_commission_paid'] or 0)
                },
                'fulfillment': {
                    **fulfillment_stats,
                    'fulfillment_rate': round(fulfillment_rate, 1)
                },
                'products': list(product_performance),
                'group_buying': {
                    'total_groups': group_stats['total_groups'] or 0,
                    'successful': group_stats['successful_groups'] or 0,
                    'failed': group_stats['failed_groups'] or 0,
                    'group_revenue': float(group_stats['total_group_revenue'] or 0)
                },
                'customers': customer_stats,
                'daily_breakdown': list(daily_breakdown)
            })

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error generating vendor performance report",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to generate performance report",
                error_code="REPORT_FAILED"
            )

    def _initiate_fsa_verification(self, vendor: Vendor) -> ServiceResult:
        """
        Initiate FSA verification for a vendor.

        Args:
            vendor: Vendor instance

        Returns:
            ServiceResult containing FSA data or error
        """
        try:
            from apps.integrations.services.fsa_service import FSAService
            fsa_service = FSAService()

            # Search for establishment
            search_result = fsa_service.search_establishment(
                vendor.business_name,
                vendor.postcode
            )

            if not search_result.success:
                self.log_warning(
                    f"FSA verification failed for vendor {vendor.id}",
                    vendor_id=vendor.id,
                    error=search_result.error
                )
                return search_result

            establishments = search_result.data

            if not establishments:
                return ServiceResult.fail(
                    "No FSA establishment found",
                    error_code="NO_FSA_MATCH"
                )

            # Take first match
            establishment = establishments[0]

            return ServiceResult.ok({
                'fsa_id': establishment['fsa_id'],
                'rating': establishment['rating_value'],
                'rating_date': establishment['rating_date'],
                'business_name': establishment['business_name']
            })

        except Exception as e:
            self.log_error(
                f"Error initiating FSA verification",
                exception=e,
                vendor_id=vendor.id
            )
            return ServiceResult.fail(
                "FSA verification failed",
                error_code="FSA_VERIFICATION_FAILED"
            )
