# apps/buying_groups/serializers.py

from rest_framework import serializers
from django.utils import timezone
from .models import BuyingGroup, GroupCommitment, GroupUpdate
from apps.products.serializers import ProductListSerializer
from apps.core.serializers import UserPublicSerializer
from apps.vendors.serializers import VendorListSerializer


class ProductForGroupSerializer(serializers.ModelSerializer):
    """Product details for buying group display - includes description"""
    vendor = VendorListSerializer(read_only=True)
    category_name = serializers.CharField(
        source='category.name', read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        from apps.products.models import Product
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'vendor', 'category_name',
            'price', 'price_with_vat', 'unit', 'primary_image', 'stock_quantity',
            'in_stock', 'contains_allergens', 'allergen_info', 'allergen_statement'
        ]


class BuyingGroupListSerializer(serializers.ModelSerializer):
    """Lightweight for group listings"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    vendor_name = serializers.CharField(
        source='product.vendor.business_name', read_only=True
    )
    time_remaining = serializers.SerializerMethodField()
    progress_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = BuyingGroup
        fields = [
            'id', 'product_name', 'vendor_name', 'area_name',
            'target_quantity', 'current_quantity', 'min_quantity', 'discount_percent',
            'progress_percent', 'time_remaining', 'expires_at', 'status'
        ]

    def get_time_remaining(self, obj):
        if obj.time_remaining:
            total_seconds = int(obj.time_remaining.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        return "Expired"


class BuyingGroupDetailSerializer(serializers.ModelSerializer):
    """Full group details with product info"""
    product = ProductForGroupSerializer(read_only=True)
    savings_per_unit = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    discounted_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    # This field is added via .annotate(participants_count=Count(...)) in get_queryset()
    # It only counts pending commitments, not all commitments
    participants_count = serializers.IntegerField(read_only=True)
    # FIX: Add progress_percent field
    progress_percent = serializers.FloatField(read_only=True)

    class Meta:
        model = BuyingGroup
        fields = [
            'id', 'product', 'center_point', 'radius_km', 'area_name',
            'target_quantity', 'current_quantity', 'min_quantity',
            'discount_percent', 'savings_per_unit', 'discounted_price',
            'created_at', 'expires_at', 'status', 'participants_count',
            'progress_percent'  # Added to fields list
        ]


class BuyingGroupCreateSerializer(serializers.ModelSerializer):
    """Create a new buying group"""

    class Meta:
        model = BuyingGroup
        fields = [
            'product', 'center_point', 'radius_km', 'area_name',
            'target_quantity', 'min_quantity', 'discount_percent',
            'expires_at'
        ]

    def validate_expires_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                "Expiry date must be in the future"
            )
        if value > timezone.now() + timezone.timedelta(days=30):
            raise serializers.ValidationError(
                "Buying groups cannot run for more than 30 days"
            )
        return value

    def validate(self, attrs):
        if attrs['min_quantity'] > attrs['target_quantity']:
            raise serializers.ValidationError(
                "Minimum quantity cannot exceed target quantity"
            )
        return attrs


class GroupCommitmentSerializer(serializers.ModelSerializer):
    """Commitment to a buying group"""
    buyer = UserPublicSerializer(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    total_savings = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )

    class Meta:
        model = GroupCommitment
        fields = [
            'id', 'group', 'buyer', 'quantity', 'buyer_postcode',
            'total_price', 'total_savings', 'status', 'committed_at',
            'order'
        ]
        read_only_fields = [
            'id', 'buyer', 'total_price', 'total_savings',
            'status', 'committed_at', 'order'
        ]

    def validate(self, attrs):
        group = attrs['group']

        # Check if group is open
        if group.status != 'open':
            raise serializers.ValidationError(
                "This buying group is no longer accepting commitments"
            )

        # Check if group has expired
        if group.is_expired:
            raise serializers.ValidationError(
                "This buying group has expired"
            )

        # Check if user already committed
        buyer = self.context['request'].user
        if GroupCommitment.objects.filter(
            group=group, buyer=buyer, status='pending'
        ).exists():
            raise serializers.ValidationError(
                "You have already committed to this group"
            )

        return attrs

    def create(self, validated_data):
        # This will be handled by service layer for Stripe integration
        validated_data['buyer'] = self.context['request'].user
        # Placeholder for location - would be geocoded
        from django.contrib.gis.geos import Point
        validated_data['buyer_location'] = Point(-0.1276, 51.5074)
        return super().create(validated_data)


class BuyingGroupRealtimeSerializer(serializers.ModelSerializer):
    """Lightweight serializer for WebSocket updates"""
    progress_percent = serializers.FloatField(read_only=True)
    time_remaining = serializers.SerializerMethodField()
    # FIX 5 & 6: Use the annotated participants_count field from the viewset
    # Don't use commitments.count which counts ALL commitments
    current_participants = serializers.IntegerField(
        source='participants_count', read_only=True
    )

    class Meta:
        model = BuyingGroup
        fields = [
            'id', 'current_quantity', 'target_quantity',
            'progress_percent', 'time_remaining', 'status',
            'current_participants'
        ]

    def get_time_remaining(self, obj):
        if obj.time_remaining:
            return int(obj.time_remaining.total_seconds())
        return 0


class GroupUpdateEventSerializer(serializers.Serializer):
    """WebSocket event message format"""
    event_type = serializers.ChoiceField(
        choices=['progress', 'threshold',
                 'expired', 'cancelled', 'status_change']
    )
    group = BuyingGroupRealtimeSerializer()
    timestamp = serializers.DateTimeField(default=timezone.now)
    message = serializers.CharField(required=False)


class GroupBuyingAnalyticsSerializer(serializers.Serializer):
    """Analytics for group buying performance"""
    success_rate = serializers.FloatField(read_only=True)
    average_discount = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True
    )
    total_savings = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    popular_products = serializers.ListField(
        child=serializers.DictField(), read_only=True
    )
