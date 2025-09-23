# apps/buying_groups/admin.py

from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.utils import timezone
from .models import BuyingGroup, GroupCommitment, GroupUpdate


@admin.register(BuyingGroup)
class BuyingGroupAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'area_name',
        'status_display',
        'progress_display',
        'discount_display',
        'time_remaining_display',
        'created_at',
        'expires_at'
    )
    list_filter = (
        'status',
        'created_at',
        'expires_at'
    )
    search_fields = (
        'product__name',
        'area_name'
    )
    readonly_fields = (
        'current_quantity',
        'last_update_at',
        'progress_percent',
        'time_remaining',
        'savings_per_unit'
    )

    fieldsets = (
        ('Product & Location', {
            'fields': (
                'product',
                'area_name',
                'center_point',
                'radius_km'
            )
        }),
        ('Group Parameters', {
            'fields': (
                'target_quantity',
                'current_quantity',
                'min_quantity',
                'discount_percent',
                'progress_percent',
                'savings_per_unit'
            )
        }),
        ('Timing', {
            'fields': (
                'expires_at',
                'time_remaining',
                'created_at',
                'last_update_at'
            )
        }),
        ('Status', {
            'fields': ('status',)
        })
    )

    def status_display(self, obj):
        colors = {
            'open': 'blue',
            'active': 'green',
            'failed': 'red',
            'completed': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def progress_display(self, obj):
        progress = obj.progress_percent
        if progress >= 100:
            color = 'green'
        elif progress >= 60:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0; border-radius: 5px;">'
            '<div style="width: {}%; background-color: {}; height: 20px; border-radius: 5px; text-align: center; color: white;">'
            '{}%</div></div>',
            min(progress, 100),
            color,
            int(progress)
        )
    progress_display.short_description = 'Progress'

    def discount_display(self, obj):
        return f"{obj.discount_percent}%"
    discount_display.short_description = 'Discount'

    def time_remaining_display(self, obj):
        if obj.time_remaining:
            days = obj.time_remaining.days
            hours = obj.time_remaining.seconds // 3600
            if days > 0:
                return f"{days}d {hours}h"
            return f"{hours}h"
        return format_html('<span style="color: red;">Expired</span>')
    time_remaining_display.short_description = 'Time Left'

    actions = ['update_status_to_active', 'update_status_to_failed']

    def update_status_to_active(self, request, queryset):
        updated = queryset.filter(current_quantity__gte=models.F(
            'min_quantity')).update(status='active')
        self.message_user(request, f'{updated} group(s) marked as active.')
    update_status_to_active.short_description = 'Mark as active'

    def update_status_to_failed(self, request, queryset):
        updated = queryset.update(status='failed')
        self.message_user(request, f'{updated} group(s) marked as failed.')
    update_status_to_failed.short_description = 'Mark as failed'


@admin.register(GroupCommitment)
class GroupCommitmentAdmin(admin.ModelAdmin):
    list_display = (
        'buyer',
        'group',
        'quantity',
        'total_price',
        'status',
        'buyer_postcode',
        'committed_at'
    )
    list_filter = (
        'status',
        'committed_at'
    )
    search_fields = (
        'buyer__email',
        'group__product__name',
        'buyer_postcode'
    )
    readonly_fields = (
        'total_price',
        'total_savings',
        'committed_at'
    )

    fieldsets = (
        ('Commitment Details', {
            'fields': (
                'group',
                'buyer',
                'quantity',
                'status'
            )
        }),
        ('Location', {
            'fields': (
                'buyer_location',
                'buyer_postcode'
            )
        }),
        ('Pricing', {
            'fields': (
                'total_price',
                'total_savings'
            )
        }),
        ('Payment', {
            'fields': ('stripe_payment_intent_id',)
        }),
        ('Timestamps', {
            'fields': ('committed_at',)
        })
    )


@admin.register(GroupUpdate)
class GroupUpdateAdmin(admin.ModelAdmin):
    list_display = (
        'group',
        'event_type',
        'created_at'
    )
    list_filter = (
        'event_type',
        'created_at'
    )
    search_fields = (
        'group__product__name',
    )
    readonly_fields = (
        'group',
        'event_type',
        'event_data',
        'created_at'
    )

    def has_add_permission(self, request):
        # These are system-generated events
        return False
