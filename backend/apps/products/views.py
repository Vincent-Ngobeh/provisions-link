"""
ViewSet implementations for product operations.
Handles product CRUD, search, and filtering.
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Prefetch
from django.utils import timezone

from apps.core.services.base import ValidationError

from .models import Product, Category, Tag
from .serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCreateUpdateSerializer,
    ProductSearchSerializer,
    CategorySerializer,
    TagSerializer
)
from .services.product_service import ProductService
from apps.buying_groups.models import BuyingGroup


class ProductPagination(PageNumberPagination):
    """Custom pagination for products."""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for product operations.
    Provides CRUD, search, and stock management.
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductListSerializer
    pagination_class = ProductPagination
    filter_backends = [DjangoFilterBackend,
                       filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'sku']
    ordering_fields = ['price', 'created_at', 'stock_quantity']
    ordering = ['-created_at']
    service = ProductService()

    def get_permissions(self):
        """Configure permissions per action."""
        if self.action in ['list', 'retrieve', 'search', 'low_stock']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ProductCreateUpdateSerializer
        elif self.action == 'search':
            return ProductSearchSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        Optimize queryset with prefetching and filtering.
        """
        queryset = super().get_queryset().select_related(
            'vendor', 'category'
        ).prefetch_related(
            'tags',
            Prefetch(
                'buying_groups',
                queryset=BuyingGroup.objects.filter(
                    status='open',
                    expires_at__gt=timezone.now()  # Only non-expired groups
                ),
                to_attr='active_groups'
            )
        )

        # CRITICAL: Only show products from vendors ready to fulfill orders
        # Staff can see everything for admin purposes
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(
                vendor__is_approved=True,  # Admin approved
                vendor__stripe_onboarding_complete=True  # Can receive payments
                # NOTE: We don't filter by FSA rating - any rating is legal
                # A 3★ vendor can still operate and is shown for transparency
            )

        # For update/delete actions, filter by vendor ownership
        if self.action in ['update', 'partial_update', 'destroy']:
            if self.request.user.is_authenticated:
                if hasattr(self.request.user, 'vendor'):
                    # Vendor can only update/delete their own products
                    queryset = queryset.filter(vendor=self.request.user.vendor)
                elif not self.request.user.is_staff:
                    # Non-vendor, non-staff users cannot update/delete
                    queryset = queryset.none()
                # Staff can access all products (no additional filter)
            else:
                queryset = queryset.none()

        # Filter by vendor if specified
        vendor_id = self.request.query_params.get('vendor')
        if vendor_id:
            queryset = queryset.filter(vendor_id=vendor_id)

        # Filter by category
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # FIXED: Filter by price range
        min_price = self.request.query_params.get('min_price')
        if min_price:
            try:
                queryset = queryset.filter(price__gte=float(min_price))
            except (ValueError, TypeError):
                pass  # Ignore invalid price values

        max_price = self.request.query_params.get('max_price')
        if max_price:
            try:
                queryset = queryset.filter(price__lte=float(max_price))
            except (ValueError, TypeError):
                pass  # Ignore invalid price values

        # Filter by stock status
        in_stock_only = self.request.query_params.get(
            'in_stock_only', 'false').lower() == 'true'
        if in_stock_only:
            queryset = queryset.filter(stock_quantity__gt=0)

        return queryset

    def perform_create(self, serializer):
        """Create product using service layer."""
        vendor = self.request.user.vendor  # User must have vendor account

        # Extract validated data
        data = serializer.validated_data.copy()

        # Transform category FK to category_id
        if 'category' in data:
            data['category_id'] = data.pop('category').id

        # Transform tags if present
        if 'tags' in data:
            data['tags'] = [tag.id for tag in data.pop('tags')]

        result = self.service.create_product(
            vendor=vendor,
            **data
        )

        if not result.success:
            raise ValidationError(result.error)

        serializer.instance = result.data

    def destroy(self, request, *args, **kwargs):
        """Soft delete products by setting is_active=False."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=['is_active'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def search(self, request):
        """
        Advanced product search with filters.
        POST /api/v1/products/search/
        """
        # Handle empty request body
        request_data = request.data if request.data else {}

        serializer = ProductSearchSerializer(data=request_data)
        serializer.is_valid(raise_exception=True)

        # Extract search parameters
        params = serializer.validated_data

        # Convert tags list to tag IDs (already integers from serializer)
        tag_ids = params.get('tags', [])

        result = self.service.search_products(
            search_query=params.get('search'),
            category_id=params.get('category').id if params.get(
                'category') else None,
            vendor_id=params.get('vendor'),
            tag_ids=tag_ids,
            min_price=params.get('min_price'),
            max_price=params.get('max_price'),
            in_stock_only=params.get('in_stock_only', False),
            allergen_free=params.get('allergen_free', []),
            min_fsa_rating=params.get('min_fsa_rating'),
            postcode=params.get('postcode'),
            radius_km=params.get('radius_km'),
            ordering=params.get('ordering', '-created_at'),
            page=request_data.get('page', 1),
            page_size=request_data.get('page_size', 20)
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def update_stock(self, request, pk=None):
        """
        Update product stock quantity.
        POST /api/products/{id}/update_stock/
        """
        product = self.get_object()

        # Check permission - only vendor owner or staff
        if product.vendor.user != request.user and not request.user.is_staff:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        quantity_change = request.data.get('quantity_change', 0)
        operation = request.data.get('operation', 'add')
        reason = request.data.get('reason')

        result = self.service.update_stock(
            product_id=product.id,
            quantity_change=int(quantity_change),
            operation=operation,
            reason=reason
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """
        Get products with low stock.
        GET /api/products/low_stock/
        """
        vendor_id = request.query_params.get('vendor')
        include_out_of_stock = request.query_params.get(
            'include_out_of_stock', 'true').lower() == 'true'

        # Permission check for vendor-specific query
        if vendor_id:
            if not request.user.is_authenticated:
                return Response({
                    'error': 'Authentication required for vendor-specific queries'
                }, status=status.HTTP_401_UNAUTHORIZED)

            # Check if user is the vendor or staff
            if not (hasattr(request.user, 'vendor') and request.user.vendor.id == int(vendor_id)) and not request.user.is_staff:
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)

        result = self.service.get_low_stock_products(
            vendor_id=int(vendor_id) if vendor_id else None,
            include_out_of_stock=include_out_of_stock
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='upload-image', parser_classes=[MultiPartParser, FormParser])
    def upload_image(self, request, pk=None):
        """
        Upload product image to S3.
        POST /api/v1/products/{id}/upload-image/
        Expects multipart/form-data with 'primary_image' field
        """
        product = self.get_object()

        # Check if user is the vendor owner or staff
        if not request.user.is_staff:
            if not hasattr(request.user, 'vendor') or product.vendor != request.user.vendor:
                return Response(
                    {'error': 'You can only upload images for your own products'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if 'primary_image' not in request.FILES:
            return Response(
                {'error': 'No image file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the uploaded file
        image_file = request.FILES['primary_image']

        # Validate file size (5MB max)
        if image_file.size > 5 * 1024 * 1024:
            return Response(
                {'error': 'Image file size must be less than 5MB'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Delete old image if exists
        if product.primary_image:
            product.primary_image.delete(save=False)

        # Save new image (automatically uploads to S3)
        product.primary_image = image_file
        product.save()

        return Response({
            'message': 'Image uploaded successfully',
            'image_url': product.primary_image.url
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'], url_path='delete-image')
    def delete_image(self, request, pk=None):
        """
        Delete product image from S3.
        DELETE /api/v1/products/{id}/delete-image/
        """
        product = self.get_object()

        # Check permissions
        if not request.user.is_staff:
            if not hasattr(request.user, 'vendor') or product.vendor != request.user.vendor:
                return Response(
                    {'error': 'You can only delete images for your own products'},
                    status=status.HTTP_403_FORBIDDEN
                )

        if product.primary_image:
            product.primary_image.delete()
            product.primary_image = None
            product.save()
            return Response({'message': 'Image deleted successfully'})

        return Response(
            {'error': 'No image to delete'},
            status=status.HTTP_404_NOT_FOUND
        )

    @action(detail=True, methods=['get'])
    def group_buying(self, request, pk=None):
        """
        Get active group buying for this product.
        GET /api/products/{id}/group_buying/
        """
        product = self.get_object()

        groups = BuyingGroup.objects.filter(
            product=product,
            status='open'
        ).order_by('-created_at')

        from apps.buying_groups.serializers import BuyingGroupListSerializer
        serializer = BuyingGroupListSerializer(groups, many=True)

        return Response({
            'product': product.name,
            'active_groups': serializer.data
        })


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product categories.
    Read-only for non-admin users.
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        """Optionally filter by parent category."""
        queryset = super().get_queryset()
        parent_id = self.request.query_params.get('parent')

        if parent_id:
            if parent_id == 'null':
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent_id=parent_id)

        return queryset.order_by('display_order', 'name')


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for product tags.
    Read-only for non-admin users.
    """
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['tag_type']

    def get_queryset(self):
        """Order by type and name."""
        return super().get_queryset().order_by('tag_type', 'name')
