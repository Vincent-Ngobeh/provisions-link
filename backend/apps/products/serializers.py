# apps/products/serializers.py

from rest_framework import serializers
from django.db import transaction
from .models import Product, Category, Tag
from apps.vendors.serializers import VendorListSerializer


class CategorySerializer(serializers.ModelSerializer):
    """Category with optional parent hierarchy"""

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'parent', 'display_order']
        read_only_fields = ['slug']


class TagSerializer(serializers.ModelSerializer):
    """Product tags for filtering"""

    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'tag_type']
        read_only_fields = ['slug']


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight product for search results"""
    vendor = VendorListSerializer(read_only=True)
    category_name = serializers.CharField(
        source='category.name', read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    active_group = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'vendor', 'category_name',
            'price', 'price_with_vat', 'unit', 'primary_image',
            'in_stock', 'contains_allergens', 'active_group'
        ]

    def get_active_group(self, obj):
        """Return active buying group if exists"""
        # This will be optimized with prefetch_related
        group = obj.buying_groups.filter(status='open').first()
        if group:
            return {
                'id': group.id,
                'discount_percent': str(group.discount_percent),
                'current_quantity': group.current_quantity,
                'target_quantity': group.target_quantity,
                'expires_at': group.expires_at
            }
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full product details"""
    vendor = VendorListSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'vendor', 'category', 'tags', 'name', 'slug',
            'description', 'sku', 'barcode', 'price', 'vat_rate',
            'price_with_vat', 'unit', 'stock_quantity',
            'low_stock_threshold', 'contains_allergens',
            'allergen_info', 'allergen_statement', 'primary_image',
            'additional_images', 'is_active', 'created_at'
        ]
        read_only_fields = ['slug', 'created_at']


class ProductCreateUpdateSerializer(serializers.ModelSerializer):
    """Product creation/update with allergen validation"""
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), required=False
    )

    class Meta:
        model = Product
        fields = [
            'category', 'name', 'description', 'sku', 'barcode',
            'price', 'vat_rate', 'unit', 'stock_quantity',
            'low_stock_threshold', 'contains_allergens',
            'allergen_info', 'allergen_statement', 'primary_image',
            'additional_images', 'tags', 'is_active'
        ]

    def validate_allergen_info(self, value):
        """Ensure allergen info has all required fields"""
        if not value:
            value = {}

        # Ensure all allergen fields are present
        for allergen in Product.ALLERGEN_FIELDS:
            if allergen not in value:
                value[allergen] = False

        return value

    def validate_sku(self, value):
        """Ensure SKU is unique for vendor"""
        vendor = self.context['request'].user.vendor
        qs = Product.objects.filter(vendor=vendor, sku=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Product with this SKU already exists for your vendor account"
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        validated_data['vendor'] = self.context['request'].user.vendor
        product = super().create(validated_data)
        product.tags.set(tags)
        return product


class ProductSearchSerializer(serializers.Serializer):
    """Validate product search parameters"""
    search = serializers.CharField(required=False, max_length=200)
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, required=False
    )
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0
    )
    max_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=0
    )
    in_stock_only = serializers.BooleanField(default=False)
    allergen_free = serializers.MultipleChoiceField(
        choices=Product.ALLERGEN_FIELDS, required=False
    )
    dietary = serializers.MultipleChoiceField(
        choices=['vegan', 'vegetarian', 'halal', 'kosher'],
        required=False
    )
    min_fsa_rating = serializers.IntegerField(
        min_value=1, max_value=5, required=False
    )
    ordering = serializers.ChoiceField(
        choices=['price', '-price', 'created_at', '-created_at', 'distance'],
        default='-created_at'
    )

    def validate(self, attrs):
        if attrs.get('min_price') and attrs.get('max_price'):
            if attrs['min_price'] > attrs['max_price']:
                raise serializers.ValidationError(
                    "Minimum price cannot exceed maximum price"
                )
        return attrs


class LocationSearchSerializer(serializers.Serializer):
    """Location-based search parameters"""
    postcode = serializers.CharField(max_length=10)
    radius_km = serializers.IntegerField(min_value=1, max_value=50, default=10)

    def validate_postcode(self, value):
        import re
        pattern = r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$'
        if not re.match(pattern, value.upper()):
            raise serializers.ValidationError("Invalid UK postcode format")
        return value.upper()


class VendorSearchSerializer(serializers.Serializer):
    """Vendor search parameters"""
    search = serializers.CharField(required=False, max_length=200)
    postcode = serializers.CharField(max_length=10, required=False)
    radius_km = serializers.IntegerField(
        min_value=1, max_value=50, default=10, required=False
    )
    min_fsa_rating = serializers.IntegerField(
        min_value=1, max_value=5, required=False
    )
    verified_only = serializers.BooleanField(default=False)
