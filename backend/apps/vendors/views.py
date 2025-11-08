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
        # For approve action, allow access to unapproved vendors
        if self.action == 'approve':
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
            vat_number=serializer.validated_data.get('vat_number'),
            logo_url=serializer.validated_data.get('logo_url')
        )

        if result.success:
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

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
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

    @action(detail=True, methods=['post'])
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
