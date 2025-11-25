"""
URL Configuration for Provisions Link
"""
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from apps.integrations.views import stripe_webhook
from apps.core.admin_site import custom_admin_site


def home_view(request):
    """API root information"""
    return JsonResponse({
        'message': 'Welcome to Provisions Link API',
        'version': '1.0.0',
        'description': 'B2B Marketplace for UK Food & Beverage Industry',
        'documentation': {
            'swagger_ui': f"{request.scheme}://{request.get_host()}/api/docs/",
            'redoc': f"{request.scheme}://{request.get_host()}/api/redoc/",
            'openapi_schema': f"{request.scheme}://{request.get_host()}/api/schema/"
        },
        'endpoints': {
            'api': '/api/v1/',
            'admin': '/admin/',
            'websocket': 'ws://localhost:8000/ws/group-buying/'
        }
    })


urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', custom_admin_site.urls),

    # API v1 endpoints
    path('api/v1/', include('provisions_link.api_urls')),

    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'),
         name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'),
         name='redoc'),

    # Stripe Webhooks (outside API versioning and auth)
    path('webhooks/stripe/', stripe_webhook, name='stripe-webhook'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)

    # Django Debug Toolbar (only if installed AND in INSTALLED_APPS)
    if 'debug_toolbar' in settings.INSTALLED_APPS:
        try:
            import debug_toolbar
            urlpatterns = [
                path('__debug__/', include(debug_toolbar.urls)),
            ] + urlpatterns
        except ImportError:
            pass
