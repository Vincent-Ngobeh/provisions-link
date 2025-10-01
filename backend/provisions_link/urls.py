"""
URL Configuration for Provisions Link
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def home_view(request):
    """Temporary homepage view"""
    return JsonResponse({
        'message': 'Welcome to Provisions Link API',
        'version': '1.0.0',
        'endpoints': {
            'admin': '/admin/',
            'api': '/api/v1/',
        }
    })


urlpatterns = [
    path('', home_view, name='home'),  # Root URL pattern
    path('admin/', admin.site.urls),
    path('api/v1/', include('provisions_link.api_urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)

    # Django Debug Toolbar (only if installed)
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass  # Debug toolbar not installed

# Admin site customization
admin.site.site_header = "Provisions Link Admin"
admin.site.site_title = "Provisions Link"
admin.site.index_title = "Welcome to Provisions Link Administration"
