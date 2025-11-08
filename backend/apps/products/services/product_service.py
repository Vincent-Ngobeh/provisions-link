"""
Product service for managing product operations.
Handles product search, filtering, stock management, and product-related business logic.
"""
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import F, Q, Sum, Count, Avg, Prefetch
from django.utils import timezone
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.paginator import Paginator
from django.contrib.gis.db.models.functions import Distance

from apps.core.services.base import (
    BaseService, ServiceResult, ValidationError,
    BusinessRuleViolation
)
from apps.products.models import Product, Category, Tag, ProductTag
from apps.vendors.models import Vendor
from apps.buying_groups.models import BuyingGroup


class ProductService(BaseService):
    """
    Service for managing product operations and search.
    """

    # Business rule constants
    MAX_PRODUCT_PRICE = Decimal('9999.99')
    MIN_PRODUCT_PRICE = Decimal('0.01')
    MAX_STOCK_QUANTITY = 99999
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # Search weights for PostgreSQL full-text search
    SEARCH_WEIGHTS = {
        'name': 'A',
        'description': 'B',
        'vendor__business_name': 'C',
        'category__name': 'D'
    }

    @transaction.atomic
    def create_product(
        self,
        vendor: Vendor,
        name: str,
        description: str,
        category_id: int,
        sku: str,
        price: Decimal,
        unit: str,
        stock_quantity: int = 0,
        vat_rate: Decimal = Decimal('0.20'),
        barcode: Optional[str] = None,
        contains_allergens: bool = False,
        allergen_info: Optional[Dict] = None,
        allergen_statement: Optional[str] = None,
        primary_image: Optional[str] = None,
        additional_images: Optional[List[str]] = None,
        tags: Optional[List[int]] = None
    ) -> ServiceResult:
        """
        Create a new product.

        Args:
            vendor: Vendor instance
            name: Product name
            description: Product description
            category_id: Category ID
            sku: Stock keeping unit
            price: Product price
            unit: Unit of measurement
            stock_quantity: Initial stock quantity
            vat_rate: VAT rate (default 20%)
            barcode: Optional EAN-13 barcode
            contains_allergens: Whether product contains allergens
            allergen_info: Dict of allergen information
            allergen_statement: Free text allergen statement
            primary_image: Primary image URL
            additional_images: List of additional image URLs
            tags: List of tag IDs

        Returns:
            ServiceResult containing created Product or error
        """
        try:
            # Validate vendor is approved
            if not vendor.is_approved:
                return ServiceResult.fail(
                    "Vendor must be approved to create products",
                    error_code="VENDOR_NOT_APPROVED"
                )

            # Validate category
            try:
                category = Category.objects.get(id=category_id, is_active=True)
            except Category.DoesNotExist:
                return ServiceResult.fail(
                    "Invalid category",
                    error_code="INVALID_CATEGORY"
                )

            # Validate SKU uniqueness for vendor
            if Product.objects.filter(vendor=vendor, sku=sku).exists():
                return ServiceResult.fail(
                    f"SKU {sku} already exists for this vendor",
                    error_code="DUPLICATE_SKU"
                )

            # Validate price
            if not self.MIN_PRODUCT_PRICE <= price <= self.MAX_PRODUCT_PRICE:
                return ServiceResult.fail(
                    f"Price must be between £{self.MIN_PRODUCT_PRICE} and £{self.MAX_PRODUCT_PRICE}",
                    error_code="INVALID_PRICE"
                )

            # Validate stock quantity
            if stock_quantity < 0 or stock_quantity > self.MAX_STOCK_QUANTITY:
                return ServiceResult.fail(
                    f"Stock quantity must be between 0 and {self.MAX_STOCK_QUANTITY}",
                    error_code="INVALID_STOCK"
                )

            # Process allergen information
            if contains_allergens and allergen_info:
                allergen_info = self._process_allergen_info(allergen_info)
            else:
                allergen_info = {}

            # Create product
            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name=name,
                description=description,
                sku=sku,
                barcode=barcode or '',
                price=price,
                vat_rate=vat_rate,
                unit=unit,
                stock_quantity=stock_quantity,
                low_stock_threshold=max(
                    10, int(stock_quantity * 0.1)),  # 10% or minimum 10
                contains_allergens=contains_allergens,
                allergen_info=allergen_info,
                allergen_statement=allergen_statement or '',
                primary_image=primary_image or '',
                additional_images=additional_images or [],
                is_active=True
            )

            # Add tags if provided
            if tags:
                valid_tags = Tag.objects.filter(id__in=tags)
                for tag in valid_tags:
                    ProductTag.objects.create(product=product, tag=tag)

            # Update search vector
            self._update_search_vector(product)

            self.log_info(
                f"Created product {product.name}",
                product_id=product.id,
                vendor_id=vendor.id,
                sku=sku
            )

            return ServiceResult.ok(product)

        except Exception as e:
            self.log_error(
                f"Error creating product",
                exception=e,
                vendor_id=vendor.id,
                name=name
            )
            return ServiceResult.fail(
                "Failed to create product",
                error_code="CREATE_FAILED"
            )

    def update_product(
        self,
        product_id: int,
        vendor: Vendor,
        **update_fields
    ) -> ServiceResult:
        """
        Update product information.

        Args:
            product_id: Product ID
            vendor: Vendor making the update
            **update_fields: Fields to update

        Returns:
            ServiceResult containing updated Product or error
        """
        try:
            # Get product and verify ownership
            try:
                product = Product.objects.get(id=product_id, vendor=vendor)
            except Product.DoesNotExist:
                return ServiceResult.fail(
                    "Product not found or you don't have permission",
                    error_code="PRODUCT_NOT_FOUND"
                )

            # Allowed fields for update
            allowed_fields = [
                'name', 'description', 'price', 'stock_quantity',
                'low_stock_threshold', 'contains_allergens',
                'allergen_info', 'allergen_statement', 'primary_image',
                'additional_images', 'is_active'
            ]

            # Process updates
            updates = {}
            for field, value in update_fields.items():
                if field not in allowed_fields:
                    continue

                # Validate specific fields
                if field == 'price':
                    if not self.MIN_PRODUCT_PRICE <= value <= self.MAX_PRODUCT_PRICE:
                        return ServiceResult.fail(
                            f"Invalid price",
                            error_code="INVALID_PRICE"
                        )

                elif field == 'stock_quantity':
                    if value < 0 or value > self.MAX_STOCK_QUANTITY:
                        return ServiceResult.fail(
                            f"Invalid stock quantity",
                            error_code="INVALID_STOCK"
                        )

                elif field == 'allergen_info' and value:
                    value = self._process_allergen_info(value)

                updates[field] = value

            # Apply updates
            for field, value in updates.items():
                setattr(product, field, value)

            product.save(update_fields=list(updates.keys()))

            # Update search vector if name or description changed
            if 'name' in updates or 'description' in updates:
                self._update_search_vector(product)

            self.log_info(
                f"Updated product {product.name}",
                product_id=product_id,
                updated_fields=list(updates.keys())
            )

            return ServiceResult.ok(product)

        except Exception as e:
            self.log_error(
                f"Error updating product",
                exception=e,
                product_id=product_id
            )
            return ServiceResult.fail(
                "Failed to update product",
                error_code="UPDATE_FAILED"
            )

    def search_products(
        self,
        search_query: Optional[str] = None,
        category_id: Optional[int] = None,
        vendor_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        in_stock_only: bool = False,
        allergen_free: Optional[List[str]] = None,
        min_fsa_rating: Optional[int] = None,
        postcode: Optional[str] = None,
        radius_km: Optional[int] = None,
        ordering: str = '-created_at',
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE
    ) -> ServiceResult:
        """
        Search and filter products with multiple criteria.

        Args:
            search_query: Text search query
            category_id: Filter by category
            vendor_id: Filter by vendor
            tag_ids: Filter by tags
            min_price: Minimum price filter
            max_price: Maximum price filter
            in_stock_only: Only show in-stock products
            allergen_free: List of allergens to exclude
            min_fsa_rating: Minimum vendor FSA rating
            postcode: Delivery postcode for location filtering
            radius_km: Delivery radius for location filtering
            ordering: Sort order
            page: Page number
            page_size: Results per page

        Returns:
            ServiceResult containing paginated products
        """
        try:
            # Base queryset
            queryset = Product.objects.select_related(
                'vendor', 'category'
            ).prefetch_related('tags').filter(is_active=True)

            # Text search
            if search_query:
                search_vector = SearchVector('name', weight='A') + \
                    SearchVector('description', weight='B') + \
                    SearchVector('vendor__business_name', weight='C')

                search_query_obj = SearchQuery(search_query)

                queryset = queryset.annotate(
                    search=search_vector,
                    rank=SearchRank(search_vector, search_query_obj)
                ).filter(search=search_query_obj).order_by('-rank')

            # Category filter
            if category_id:
                queryset = queryset.filter(category_id=category_id)

            # Vendor filter
            if vendor_id:
                queryset = queryset.filter(vendor_id=vendor_id)

            # Tag filter
            if tag_ids:
                queryset = queryset.filter(tags__id__in=tag_ids).distinct()

            # Price range filter
            if min_price is not None:
                queryset = queryset.filter(price__gte=min_price)

            if max_price is not None:
                queryset = queryset.filter(price__lte=max_price)

            # Stock filter
            if in_stock_only:
                queryset = queryset.filter(stock_quantity__gt=0)

            # Allergen filter
            if allergen_free:
                for allergen in allergen_free:
                    queryset = queryset.exclude(
                        allergen_info__contains={allergen: True}
                    )

            # FSA rating filter
            if min_fsa_rating:
                queryset = queryset.filter(
                    vendor__fsa_rating_value__gte=min_fsa_rating,
                    vendor__fsa_verified=True
                )

            # Location-based filtering
            if postcode and radius_km:
                from apps.integrations.services.geocoding_service import GeocodingService
                geo_service = GeocodingService()

                location_result = geo_service.geocode_postcode(postcode)

                if location_result.success:
                    delivery_point = location_result.data['point']

                    # Filter vendors within delivery range
                    from django.contrib.gis.measure import D
                    queryset = queryset.filter(
                        vendor__location__distance_lte=(
                            delivery_point, D(km=radius_km))
                    )

                    # Annotate with distance
                    queryset = queryset.annotate(
                        distance=Distance('vendor__location', delivery_point)
                    )

            # Apply ordering
            valid_orderings = {
                'price': 'price',
                '-price': '-price',
                'created_at': 'created_at',
                '-created_at': '-created_at',
                'name': 'name',
                '-name': '-name',
                'stock': 'stock_quantity',
                '-stock': '-stock_quantity'
            }

            if ordering in valid_orderings:
                queryset = queryset.order_by(valid_orderings[ordering])
            elif ordering == 'distance' and postcode:
                queryset = queryset.order_by('distance')

            # Check for active buying groups
            queryset = queryset.prefetch_related(
                Prefetch(
                    'buying_groups',
                    queryset=BuyingGroup.objects.filter(status='open'),
                    to_attr='active_groups'
                )
            )

            # Pagination
            page_size = min(page_size, self.MAX_PAGE_SIZE)
            paginator = Paginator(queryset, page_size)

            try:
                page_obj = paginator.page(page)
            except:
                return ServiceResult.fail(
                    "Invalid page number",
                    error_code="INVALID_PAGE"
                )

            # Format results
            products = []
            for product in page_obj:
                # Safely get primary image URL
                primary_image_url = None
                if product.primary_image and product.primary_image.name not in ('', None):
                    try:
                        primary_image_url = product.primary_image.url
                    except (ValueError, AttributeError):
                        pass

                product_data = {
                    'id': product.id,
                    'name': product.name,
                    'description': product.description[:200],
                    'vendor': {
                        'id': product.vendor.id,
                        'name': product.vendor.business_name,
                        'fsa_rating': product.vendor.fsa_rating_value
                    },
                    'category': {
                        'id': product.category.id,
                        'name': product.category.name
                    },
                    'price': float(product.price),
                    'vat_rate': float(product.vat_rate),
                    'price_with_vat': float(product.price_with_vat),
                    'unit': product.unit,
                    'in_stock': product.in_stock,
                    'stock_quantity': product.stock_quantity,
                    'contains_allergens': product.contains_allergens,
                    'primary_image': primary_image_url,
                    'tags': [
                        {'id': tag.id, 'name': tag.name}
                        for tag in product.tags.all()
                    ]
                }

                # Add active group info if exists
                if hasattr(product, 'active_groups') and product.active_groups:
                    group = product.active_groups[0]
                    product_data['active_group'] = {
                        'id': group.id,
                        'discount_percent': float(group.discount_percent),
                        'current_quantity': group.current_quantity,
                        'target_quantity': group.target_quantity,
                        'expires_at': group.expires_at,
                        'progress_percent': float(group.progress_percent)
                    }

                # Add distance if location search
                if hasattr(product, 'distance'):
                    product_data['distance_km'] = float(product.distance.km)

                products.append(product_data)

            return ServiceResult.ok({
                'products': products,
                'count': paginator.count,
                'next': f'?page={page + 1}' if page_obj.has_next() else None,
                'previous': f'?page={page - 1}' if page_obj.has_previous() else None,
                'results': products,
                'radius_km': radius_km
            })

        except Exception as e:
            self.log_error(
                f"Error searching products",
                exception=e
            )
            return ServiceResult.fail(
                "Failed to search products",
                error_code="SEARCH_FAILED"
            )

    def update_stock(
        self,
        product_id: int,
        quantity_change: int,
        operation: str = 'add',
        reason: Optional[str] = None
    ) -> ServiceResult:
        """
        Update product stock quantity.

        Args:
            product_id: Product ID
            quantity_change: Amount to add or subtract
            operation: 'add' or 'subtract'
            reason: Reason for stock change

        Returns:
            ServiceResult with updated stock info
        """
        try:
            with transaction.atomic():
                product = Product.objects.select_for_update().get(id=product_id)

                if operation == 'add':
                    new_quantity = product.stock_quantity + quantity_change
                elif operation == 'subtract':
                    new_quantity = product.stock_quantity - quantity_change
                else:
                    return ServiceResult.fail(
                        "Invalid operation",
                        error_code="INVALID_OPERATION"
                    )

                # Validate new quantity
                if new_quantity < 0:
                    return ServiceResult.fail(
                        "Insufficient stock",
                        error_code="INSUFFICIENT_STOCK"
                    )

                if new_quantity > self.MAX_STOCK_QUANTITY:
                    return ServiceResult.fail(
                        f"Stock cannot exceed {self.MAX_STOCK_QUANTITY}",
                        error_code="EXCEEDS_MAX_STOCK"
                    )

                # Update stock
                old_quantity = product.stock_quantity
                product.stock_quantity = new_quantity
                product.save(update_fields=['stock_quantity'])

                self.log_info(
                    f"Updated stock for product {product.name}",
                    product_id=product_id,
                    old_quantity=old_quantity,
                    new_quantity=new_quantity,
                    operation=operation,
                    reason=reason
                )

                # Check if low stock alert needed
                low_stock_alert = (
                    new_quantity <= product.low_stock_threshold and
                    old_quantity > product.low_stock_threshold
                )

                return ServiceResult.ok({
                    'product_id': product_id,
                    'old_quantity': old_quantity,
                    'new_quantity': new_quantity,
                    'low_stock_alert': low_stock_alert,
                    'out_of_stock': new_quantity == 0
                })

        except Product.DoesNotExist:
            return ServiceResult.fail(
                f"Product {product_id} not found",
                error_code="PRODUCT_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error updating stock",
                exception=e,
                product_id=product_id
            )
            return ServiceResult.fail(
                "Failed to update stock",
                error_code="UPDATE_FAILED"
            )

    def get_low_stock_products(
        self,
        vendor_id: Optional[int] = None,
        include_out_of_stock: bool = True
    ) -> ServiceResult:
        """
        Get products with low stock.

        Args:
            vendor_id: Filter by vendor
            include_out_of_stock: Include products with zero stock

        Returns:
            ServiceResult containing low stock products
        """
        try:
            queryset = Product.objects.filter(
                is_active=True,
                stock_quantity__lte=F('low_stock_threshold')
            ).select_related('vendor', 'category')

            if not include_out_of_stock:
                queryset = queryset.filter(stock_quantity__gt=0)

            if vendor_id:
                queryset = queryset.filter(vendor_id=vendor_id)

            queryset = queryset.order_by('stock_quantity', 'name')

            products = []
            for product in queryset[:100]:  # Limit to 100 products
                products.append({
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'vendor': product.vendor.business_name,
                    'stock_quantity': product.stock_quantity,
                    'low_stock_threshold': product.low_stock_threshold,
                    'percentage_remaining': round(
                        (product.stock_quantity / product.low_stock_threshold * 100)
                        if product.low_stock_threshold > 0 else 0,
                        1
                    )
                })

            return ServiceResult.ok({
                'products': products,
                'count': len(products),
                'out_of_stock_count': sum(1 for p in products if p['stock_quantity'] == 0)
            })

        except Exception as e:
            self.log_error(
                f"Error getting low stock products",
                exception=e
            )
            return ServiceResult.fail(
                "Failed to get low stock products",
                error_code="FETCH_FAILED"
            )

    def _process_allergen_info(self, allergen_info: Dict) -> Dict:
        """
        Process and validate allergen information.

        Args:
            allergen_info: Raw allergen information

        Returns:
            Processed allergen information
        """
        # Ensure all allergen fields are present
        processed = {}

        for allergen in Product.ALLERGEN_FIELDS:
            processed[allergen] = allergen_info.get(allergen, False)

        return processed

    def _update_search_vector(self, product: Product) -> None:
        """
        Update PostgreSQL search vector for a product.

        Args:
            product: Product instance
        """
        try:
            # Build search vector from multiple fields
            search_vector = SearchVector('name', weight='A') + \
                SearchVector('description', weight='B') + \
                SearchVector('sku', weight='C')

            Product.objects.filter(id=product.id).update(
                search_vector=search_vector
            )
        except Exception as e:
            self.log_error(
                f"Error updating search vector",
                exception=e,
                product_id=product.id
            )
