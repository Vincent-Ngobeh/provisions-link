# apps/vendors/serializers.py

from rest_framework import serializers
from django.contrib.gis.geos import Point
from .models import Vendor
from apps.core.serializers import UserPublicSerializer


class VendorListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for vendor listings/search results"""
    fsa_rating_display = serializers.CharField(read_only=True)
    distance_km = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True,
        required=False  # Only present when location filtering
    )
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            'id', 'business_name', 'slug', 'description',
            'fsa_rating_value', 'fsa_rating_display',
            'delivery_radius_km', 'min_order_value',
            'logo_url', 'distance_km',
            'postcode',
            'is_approved',
            'stripe_onboarding_complete',
        ]

    def get_logo_url(self, obj):
        """Return the logo URL if it exists."""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None


class VendorDetailSerializer(serializers.ModelSerializer):
    """Detailed vendor profile for vendor page"""
    user = UserPublicSerializer(read_only=True)
    products_count = serializers.IntegerField(read_only=True)
    active_groups_count = serializers.IntegerField(read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            'id', 'user', 'business_name', 'slug', 'description',
            'phone_number', 'is_approved', 'fsa_verified',
            'location', 'postcode', 'delivery_radius_km',
            'fsa_rating_value', 'fsa_rating_date', 'fsa_rating_display',
            'min_order_value', 'logo_url', 'created_at',
            'products_count', 'active_groups_count'
        ]
        read_only_fields = [
            'id', 'slug', 'is_approved', 'fsa_verified',
            'fsa_rating_value', 'fsa_rating_date', 'created_at'
        ]

    def get_logo_url(self, obj):
        """Return the logo URL if it exists."""
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None


class VendorRegistrationSerializer(serializers.ModelSerializer):
    """Vendor registration with location geocoding"""
    postcode = serializers.CharField(max_length=10)
    logo = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Vendor
        fields = [
            'business_name', 'description', 'phone_number',
            'postcode', 'delivery_radius_km', 'min_order_value',
            'vat_number', 'logo'
        ]

    def validate_postcode(self, value):
        """Validate and geocode postcode"""
        # This will be handled by the service layer
        # Currently validates format only
        import re
        pattern = r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$'
        if not re.match(pattern, value.upper()):
            raise serializers.ValidationError("Invalid UK postcode")
        return value.upper()

    def create(self, validated_data):
        # Extract postcode for geocoding
        postcode = validated_data.get('postcode')
        # In production, this would call geocoding service
        validated_data['location'] = Point(-0.1276, 51.5074)  # London

        # Create vendor linked to current user
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class VendorDashboardSerializer(serializers.ModelSerializer):
    """Vendor's own dashboard data"""
    today_revenue = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    pending_orders = serializers.IntegerField(read_only=True)
    low_stock_products = serializers.IntegerField(read_only=True)

    class Meta:
        model = Vendor
        fields = [
            'id', 'business_name', 'stripe_onboarding_complete',
            'commission_rate', 'today_revenue', 'pending_orders',
            'low_stock_products', 'fsa_rating_value', 'fsa_last_checked'
        ]


class VendorAnalyticsSerializer(serializers.Serializer):
    """Vendor analytics data"""
    period = serializers.ChoiceField(
        choices=['day', 'week', 'month', 'year'], default='week'
    )
    revenue_data = serializers.ListField(
        child=serializers.DictField(), read_only=True
    )
    top_products = serializers.ListField(
        child=serializers.DictField(), read_only=True
    )
    order_stats = serializers.DictField(read_only=True)
    group_buying_stats = serializers.DictField(read_only=True)
