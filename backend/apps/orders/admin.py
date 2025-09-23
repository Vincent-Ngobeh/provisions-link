# apps/orders/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('vat_amount',)
    fields = ('product', 'quantity', 'unit_price',
              'total_price', 'discount_amount', 'vat_amount')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'reference_number',
        'buyer_link',
        'vendor_link',
        'status_display',
        'total_display',
        'group',
        'created_at',
        'paid_at'
    )
    list_filter = (
        'status',
        'created_at',
        'paid_at',
        'vendor'
    )
    search_fields = (
        'reference_number',
        'buyer__email',
        'vendor__business_name',
        'stripe_payment_intent_id'
    )
    readonly_fields = (
        'reference_number',
        'marketplace_fee',
        'vendor_payout',
        'created_at',
        'paid_at',
        'delivered_at'
    )
    inlines = [OrderItemInline]

    fieldsets = (
        ('Order Information', {
            'fields': (
                'reference_number',
                'buyer',
                'vendor',
                'group',
                'status'
            )
        }),
        ('Delivery', {
            'fields': (
                'delivery_address',
                'delivery_notes'
            )
        }),
        ('Pricing', {
            'fields': (
                'subtotal',
                'vat_amount',
                'delivery_fee',
                'total',
                'marketplace_fee',
                'vendor_payout'
            )
        }),
        ('Payment', {
            'fields': ('stripe_payment_intent_id',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'paid_at',
                'delivered_at'
            )
        })
    )

    def buyer_link(self, obj):
        url = reverse('admin:core_user_change', args=[obj.buyer.id])
        return format_html('<a href="{}">{}</a>', url, obj.buyer.email)
    buyer_link.short_description = 'Buyer'

    def vendor_link(self, obj):
        url = reverse('admin:vendors_vendor_change', args=[obj.vendor.id])
        return format_html('<a href="{}">{}</a>', url, obj.vendor.business_name)
    vendor_link.short_description = 'Vendor'

    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'paid': 'blue',
            'processing': 'lightblue',
            'shipped': 'purple',
            'delivered': 'green',
            'cancelled': 'red',
            'refunded': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def total_display(self, obj):
        return f"£{obj.total:.2f}"
    total_display.short_description = 'Total'

    actions = ['mark_as_paid', 'mark_as_processing',
               'mark_as_shipped', 'mark_as_delivered']

    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='pending').update(
            status='paid',
            paid_at=timezone.now()
        )
        self.message_user(request, f'{updated} order(s) marked as paid.')
    mark_as_paid.short_description = 'Mark as paid'

    def mark_as_processing(self, request, queryset):
        updated = queryset.filter(status='paid').update(status='processing')
        self.message_user(request, f'{updated} order(s) marked as processing.')
    mark_as_processing.short_description = 'Mark as processing'

    def mark_as_shipped(self, request, queryset):
        updated = queryset.filter(status='processing').update(status='shipped')
        self.message_user(request, f'{updated} order(s) marked as shipped.')
    mark_as_shipped.short_description = 'Mark as shipped'

    def mark_as_delivered(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='shipped').update(
            status='delivered',
            delivered_at=timezone.now()
        )
        self.message_user(request, f'{updated} order(s) marked as delivered.')
    mark_as_delivered.short_description = 'Mark as delivered'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            # Recalculate totals when order is saved
            obj.calculate_totals()


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order_link',
        'product',
        'quantity',
        'unit_price',
        'total_price',
        'discount_amount'
    )
    list_filter = ('order__created_at',)
    search_fields = (
        'order__reference_number',
        'product__name',
        'product__sku'
    )
    readonly_fields = ('vat_amount',)

    def order_link(self, obj):
        url = reverse('admin:orders_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.reference_number)
    order_link.short_description = 'Order'
