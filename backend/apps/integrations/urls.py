"""
URL configuration for integration endpoints.
Groups all external service integrations.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    FSAIntegrationViewSet,
    GeocodingViewSet,
    StripeIntegrationViewSet,
    stripe_webhook
)

# Create router for integration viewsets
router = DefaultRouter()
router.register(r'fsa', FSAIntegrationViewSet, basename='fsa-integration')
router.register(r'geocoding', GeocodingViewSet, basename='geocoding')
router.register(r'stripe', StripeIntegrationViewSet,
                basename='stripe-integration')

app_name = 'integrations'

urlpatterns = [
    # Router URLs
    path('', include(router.urls)),

    # Webhook endpoints (these are outside auth)
    # Note: Main webhook is in main urls.py for clarity
]
