"""
ViewSet implementations for vendor operations.
Connects service layer to REST API endpoints.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Count, Avg, Q
from django.utils import timezone

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

from .models import Vendor
from .serializers import (
    VendorListSerializer,
    VendorDetailSerializer,
    VendorRegistrationSerializer,
    VendorDashboardSerializer,
    VendorAnalyticsSerializer
)
from .services.vendor_service import VendorService
from apps.products.models import Product
from apps.buying_groups.models import BuyingGroup


@extend_schema_view(
    list=extend_schema(
        summary="List all approved vendors",
        description="""
        Retrieve a list of approved vendors ready to fulfill orders.
 
        **Includes vendor statistics:**
        - Active product count
        - Open buying groups count
        - FSA food hygiene rating
 
        **Filtering:**
        - Search by business name or description
        - Location-based search (postcode + radius)
        - FSA rating filtering
        """,
        parameters=[
            OpenApiParameter('search', Types.STR,
                             description='Search vendor name/description'),
            OpenApiParameter('near_postcode', Types.STR,
                             description='Find vendors near postcode'),
            OpenApiParameter('radius_km', Types.INT,
                             description='Search radius in km (default: 10)'),
            OpenApiParameter('min_rating', Types.INT,
                             description='Minimum FSA rating (1-5)'),
        ],
        tags=['Vendors']
    ),
    retrieve=extend_schema(
        summary="Get vendor details",
        description="""
        Retrieve detailed information about a specific vendor.
 
        **Includes:**
        - Full vendor profile with business information
        - Contact details and location
        - FSA food hygiene rating
        - Delivery radius and minimum order value
        - Stripe onboarding status
        - Active products list
        - Customer reviews and ratings
 
        **Permissions:** Public (no authentication required)
        """,
        tags=['Vendors']
    ),
    create=extend_schema(
        summary="Create vendor (admin only)",
        description="""
        Create a new vendor account directly (admin only).
        Regular users should use the /register/ endpoint instead.
 
        **Permissions:** Admin/staff only
        """,
        tags=['Vendors']
    ),
    update=extend_schema(
        summary="Update vendor details",
        description="""
        Update all fields of a vendor account.
 
        **Permissions:** Vendor owner or admin only
        """,
        tags=['Vendors']
    ),
    partial_update=extend_schema(
        summary="Partially update vendor details",
        description="""
        Update specific fields of a vendor account.
 
        **Permissions:** Vendor owner or admin only
        """,
        tags=['Vendors']
    ),
    destroy=extend_schema(
        summary="Delete vendor account",
        description="""
        Delete or deactivate a vendor account.
        May require completing all pending orders first.
 
        **Permissions:** Vendor owner or admin only
        """,
        tags=['Vendors']
    ),
)
class VendorViewSet(viewsets.ModelViewSet):
    """
    ViewSet for vendor operations.
    Provides CRUD + custom actions for vendor management.
    """
    queryset = Vendor.objects.filter(is_approved=True)
    serializer_class = VendorListSerializer
    service = VendorService()

    def get_permissions(self):
        """
        Instantiate and return the list of permissions required.
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [AllowAny]
        elif self.action == 'register':
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return VendorDetailSerializer
        elif self.action == 'register':
            return VendorRegistrationSerializer
        elif self.action == 'dashboard':
            return VendorDashboardSerializer
        elif self.action == 'analytics':
            return VendorAnalyticsSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        Optionally filter vendors by location or other criteria.
        """
        # For specific vendor actions (dashboard, onboarding), allow owner/staff access to unapproved vendors
        if self.action in ['approve', 'dashboard', 'generate_onboarding_link']:
            queryset = Vendor.objects.all()
        else:
            queryset = Vendor.objects.filter(is_approved=True)

        # Add annotations for list view
        if self.action == 'list':
            queryset = queryset.annotate(
                products_count=Count(
                    'products', filter=Q(products__is_active=True)),
                active_groups_count=Count('products__buying_groups',
                                          filter=Q(products__buying_groups__status='open'))
            )

        # Search filtering by name or description
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(business_name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Location-based filtering
        postcode = self.request.query_params.get('near_postcode')
        radius_km = self.request.query_params.get('radius_km', 10)

        if postcode:
            # Use service for location search
            result = self.service.search_vendors_by_location(
                postcode=postcode,
                radius_km=int(radius_km),
                min_rating=self.request.query_params.get('min_rating'),
                only_verified=self.request.query_params.get(
                    'verified_only', False),
                category_id=self.request.query_params.get('category')
            )
            if result.success:
                vendor_ids = [v['id'] for v in result.data['vendors']]
                queryset = queryset.filter(id__in=vendor_ids)

        return queryset

    @extend_schema(
        summary="Register a new vendor account",
        description="""
        Register as a vendor on the Provisions Link marketplace.
 
        **Process:**
        1. Creates vendor profile with business information
        2. Geocodes postcode for location-based features
        3. Verifies FSA food hygiene rating (if available)
        4. Initiates Stripe Connect onboarding for payment processing
        5. Pending admin approval before going live
 
        **Requirements:**
        - Must be authenticated
        - Valid UK postcode
        - Business name and description
        - Delivery radius and minimum order value
 
        **Example Request:**
```json
        {
            "business_name": "Farm Fresh Organics",
            "description": "Locally sourced organic vegetables and fruits",
            "postcode": "SW1A 1AA",
            "delivery_radius_km": 15,
            "min_order_value": 25.00,
            "phone_number": "+44 20 1234 5678",
            "vat_number": "GB123456789",
            "logo": "<file upload>"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=VendorRegistrationSerializer,
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'vendor': {'type': 'object'},
                    'onboarding_url': {'type': 'string', 'format': 'uri'},
                    'fsa_verified': {'type': 'boolean'},
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Vendors']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def register(self, request):
        """
        Register a new vendor account.
        POST /api/vendors/register/
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Use service layer for business logic
        result = self.service.register_vendor(
            user=request.user,
            business_name=serializer.validated_data['business_name'],
            description=serializer.validated_data['description'],
            postcode=serializer.validated_data['postcode'],
            delivery_radius_km=serializer.validated_data['delivery_radius_km'],
            min_order_value=serializer.validated_data['min_order_value'],
            phone_number=serializer.validated_data.get('phone_number'),
            vat_number=serializer.validated_data.get('vat_number')
        )

        if result.success:
            # Handle logo upload if provided
            logo = serializer.validated_data.get('logo')
            if logo:
                vendor = result.data['vendor']
                vendor.logo = logo
                vendor.save(update_fields=['logo'])

            vendor_data = VendorDetailSerializer(result.data['vendor']).data
            return Response({
                'vendor': vendor_data,
                'onboarding_url': result.data.get('onboarding_url'),
                'fsa_verified': result.data.get('fsa_verified'),
                'message': 'Vendor registered successfully. Pending admin approval.'
            }, status=status.HTTP_201_CREATED)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get vendor dashboard metrics",
        description="""
        Retrieve comprehensive dashboard metrics for vendor account management.
 
        **Metrics Included:**
        - Total revenue (lifetime and monthly)
        - Order statistics (pending, completed, cancelled)
        - Product performance (views, conversions, low stock alerts)
        - Active buying groups count
        - Recent orders and activities
        - Stripe payout information
 
        **Use Cases:**
        - Vendor dashboard homepage
        - Business analytics and reporting
        - Inventory management alerts
        - Revenue tracking
 
        **Permissions:** Vendor owner or admin only
        """,
        responses={200: VendorDashboardSerializer},
        tags=['Vendors']
    )
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated], url_path='dashboard')
    def dashboard(self, request, pk=None):
        """
        Get vendor dashboard metrics.
        GET /api/vendors/{id}/dashboard/
        """
        vendor = self.get_object()

        # Check permission - only vendor owner or staff
        if vendor.user != request.user and not request.user.is_staff:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        # Get metrics from service
        result = self.service.get_vendor_dashboard_metrics(vendor.id)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Approve a vendor account",
        description="""
        Admin action to approve a pending vendor registration.
 
        **Process:**
        1. Sets vendor status to approved
        2. Configures commission rate for the vendor
        3. Enables vendor to list products and accept orders
        4. Sends approval notification to vendor
 
        **Requirements:**
        - Admin/staff access only
        - Vendor must have completed Stripe onboarding
        - Commission rate must be specified (default: 10%)
 
        **Example Request:**
```json
        {
            "commission_rate": 0.10
        }
```
 
        **Permissions:** Admin/staff only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'commission_rate': {'type': 'number', 'format': 'decimal', 'description': 'Commission rate (e.g., 0.10 for 10%)'}
                }
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'vendor': {'type': 'object'}
                }
            }
        },
        tags=['Vendors']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        """
        Approve a vendor (admin only).
        POST /api/vendors/{id}/approve/
        """
        if not request.user.is_staff:
            return Response({
                'error': 'Admin access required'
            }, status=status.HTTP_403_FORBIDDEN)

        vendor = self.get_object()
        commission_rate = request.data.get('commission_rate')

        if commission_rate is not None:
            try:
                from decimal import Decimal
                commission_rate = Decimal(str(commission_rate))
            except (ValueError, TypeError):
                return Response({
                    'error': 'Invalid commission rate format'
                }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.approve_vendor(
            vendor_id=vendor.id,
            admin_user=request.user,
            commission_rate=commission_rate
        )

        if result.success:
            return Response({
                'message': 'Vendor approved successfully',
                'vendor': VendorDetailSerializer(result.data['vendor']).data
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Generate Stripe Connect onboarding link",
        description="""
        Generate a Stripe Connect onboarding URL for vendor payment setup.
 
        **Purpose:**
        - Allows vendors to complete Stripe Connect onboarding
        - Required before vendor can accept payments
        - Creates or updates Stripe Connect account
        - Returns secure onboarding URL
 
        **Process:**
        1. Creates Stripe Connect account (if not exists)
        2. Generates account link for onboarding
        3. Vendor completes identity verification and banking details
        4. Returns to refresh URL after completion
 
        **Use Cases:**
        - Initial vendor registration
        - Re-onboarding after account issues
        - Updating banking information
 
        **Permissions:** Vendor owner or admin only
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'url': {'type': 'string', 'format': 'uri', 'description': 'Stripe onboarding URL'},
                    'expires_at': {'type': 'integer', 'description': 'Unix timestamp when link expires'}
                }
            }
        },
        tags=['Vendors']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='generate_onboarding_link')
    def generate_onboarding_link(self, request, pk=None):
        """
        Generate Stripe Connect onboarding link.
        POST /api/vendors/{id}/generate_onboarding_link/
        """
        vendor = self.get_object()

        # Check permission
        if vendor.user != request.user and not request.user.is_staff:
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)

        from apps.integrations.services.stripe_service import StripeConnectService
        stripe_service = StripeConnectService()

        result = stripe_service.generate_onboarding_link(vendor)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Search vendors by delivery location",
        description="""
        Find vendors that deliver to a specific postcode within a given radius.
 
        **Search Features:**
        - Geocodes postcode to coordinates
        - Finds vendors within delivery radius
        - Filters by minimum FSA rating (optional)
        - Filter by verified vendors only (optional)
        - Filter by product category (optional)
 
        **Query Parameters:**
        - `postcode` (required): UK postcode to search from
        - `radius_km` (optional): Search radius in kilometers (default: 10)
        - `min_rating` (optional): Minimum FSA hygiene rating (1-5)
        - `verified_only` (optional): Only show verified vendors (default: false)
        - `category` (optional): Filter vendors by product category ID
 
        **Example Request:**
```
        GET /api/vendors/search_by_location/?postcode=SW1A1AA&radius_km=15&min_rating=4
```
 
        **Use Cases:**
        - Location-based vendor discovery
        - Delivery availability checker
        - Local vendor browsing
 
        **Permissions:** Public (no authentication required)
        """,
        parameters=[
            OpenApiParameter(
                name='postcode',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description='UK postcode to search from (e.g., SW1A 1AA)'
            ),
            OpenApiParameter(
                name='radius_km',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Search radius in kilometers (default: 10)',
                examples=[
                    OpenApiExample('5km radius', value=5),
                    OpenApiExample('10km radius', value=10),
                    OpenApiExample('20km radius', value=20),
                ]
            ),
            OpenApiParameter(
                name='min_rating',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Minimum FSA hygiene rating (1-5)'
            ),
            OpenApiParameter(
                name='verified_only',
                type=Types.BOOL,
                location=OpenApiParameter.QUERY,
                description='Only show verified vendors (default: false)'
            ),
            OpenApiParameter(
                name='category',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by product category ID'
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'vendors': {'type': 'array'},
                    'count': {'type': 'integer'},
                    'search_location': {'type': 'object'}
                }
            }
        },
        tags=['Vendors']
    )
    @action(detail=False, methods=['get'])
    def search_by_location(self, request):
        """
        Search vendors by delivery location.
        GET /api/vendors/search_by_location/?postcode=SW1A1AA&radius_km=10
        """
        postcode = request.query_params.get('postcode')
        if not postcode:
            return Response({
                'error': 'Postcode parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        radius_km = int(request.query_params.get('radius_km', 10))
        min_rating = request.query_params.get('min_rating')
        only_verified = request.query_params.get(
            'verified_only', 'false').lower() == 'true'
        category_id = request.query_params.get('category')

        result = self.service.search_vendors_by_location(
            postcode=postcode,
            radius_km=radius_km,
            min_rating=int(min_rating) if min_rating else None,
            only_verified=only_verified,
            category_id=int(category_id) if category_id else None
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error
        }, status=status.HTTP_400_BAD_REQUEST)
