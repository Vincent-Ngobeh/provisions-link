"""
Main API URL configuration for Provisions Link.
Consolidates all app API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView
)

# Import ViewSets from all apps
from apps.vendors.views import VendorViewSet
from apps.products.views import ProductViewSet, CategoryViewSet, TagViewSet
from apps.buying_groups.views import BuyingGroupViewSet, GroupCommitmentViewSet
from apps.orders.views import OrderViewSet
from apps.core.views import UserViewSet, AddressViewSet

# Create main router
router = DefaultRouter()

# Register all ViewSets
router.register(r'vendors', VendorViewSet, basename='vendor')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'buying-groups', BuyingGroupViewSet, basename='buyinggroup')
router.register(r'group-commitments', GroupCommitmentViewSet,
                basename='groupcommitment')
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'users', UserViewSet, basename='user')
router.register(r'addresses', AddressViewSet, basename='address')

# API URL patterns
urlpatterns = [
    # JWT Authentication endpoints
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # Router URLs
    path('', include(router.urls)),

    # Custom integration endpoints
    path('integrations/', include('apps.integrations.urls')),

    # Stripe webhooks (outside authentication)
    path('webhooks/stripe/', include('apps.integrations.webhooks')),
]
