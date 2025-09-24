# apps/products/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Tag, Product, ProductTag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'display_order', 'is_active', 'slug')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('display_order', 'name')


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag_type', 'slug')
    list_filter = ('tag_type',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('tag_type', 'name')


# Move ProductTagAdmin outside and create inline version
@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ('product', 'tag')
    list_filter = ('tag__tag_type', 'tag')
    search_fields = ('product__name', 'tag__name')


class ProductTagInline(admin.TabularInline):
    """Inline admin for managing product tags"""
    model = ProductTag
    extra = 1
    autocomplete_fields = ['tag']  # Makes tag selection easier


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'vendor',
        'category',
        'sku',
        'price_display',
        'stock_display',
        'contains_allergens',
        'is_active',
        'featured',
        'created_at'
    )
    list_filter = (
        'is_active',
        'featured',
        'contains_allergens',
        'category',
        'vendor',
        'created_at'
    )
    search_fields = (
        'name',
        'sku',
        'barcode',
        'vendor__business_name',
        'description'
    )
    readonly_fields = (
        'slug',
        'created_at',
        'updated_at'
    )

    inlines = [ProductTagInline]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'vendor',
                'category',
                'name',
                'slug',
                'description',

            )
        }),
        ('Product Codes', {
            'fields': (
                'sku',
                'barcode'
            )
        }),
        ('Pricing & Units', {
            'fields': (
                'price',
                'vat_rate',
                'unit'
            )
        }),
        ('Stock Management', {
            'fields': (
                'stock_quantity',
                'low_stock_threshold'
            )
        }),
        ('Allergen Information', {
            'fields': (
                'contains_allergens',
                'allergen_info',
                'allergen_statement'
            ),
            'classes': ('collapse',)
        }),
        ('Media', {
            'fields': (
                'primary_image',
                'additional_images'
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': (
                'is_active',
                'featured'
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )

    def price_display(self, obj):
        return f"£{obj.price:.2f}"
    price_display.short_description = 'Price'

    def stock_display(self, obj):
        if obj.stock_quantity == 0:
            return format_html('<span style="color: red;">Out of Stock</span>')
        elif obj.low_stock:
            return format_html(
                '<span style="color: orange;">Low ({} {})</span>',
                obj.stock_quantity,
                obj.unit
            )
        return format_html(
            '<span style="color: green;">{} {}</span>',
            obj.stock_quantity,
            obj.unit
        )
    stock_display.short_description = 'Stock'

    actions = ['activate_products', 'deactivate_products',
               'mark_featured', 'unmark_featured']

    def activate_products(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} product(s) activated.')
    activate_products.short_description = 'Activate selected products'

    def deactivate_products(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} product(s) deactivated.')
    deactivate_products.short_description = 'Deactivate selected products'

    def mark_featured(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f'{updated} product(s) marked as featured.')
    mark_featured.short_description = 'Mark as featured'

    def unmark_featured(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(
            request, f'{updated} product(s) unmarked as featured.')
    unmark_featured.short_description = 'Remove from featured'
