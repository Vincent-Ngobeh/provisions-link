# apps/vendors/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        'business_name',
        'user',
        'postcode',
        'delivery_radius_km',
        'fsa_rating_display_admin',
        'is_approved',
        'stripe_status',
        'commission_rate_display',
        'created_at'
    )
    list_filter = (
        'is_approved',
        'fsa_verified',
        'stripe_onboarding_complete',
        'fsa_rating_value',
        'created_at'
    )
    search_fields = (
        'business_name',
        'user__email',
        'postcode',
        'vat_number'
    )
    readonly_fields = (
        'slug',
        'fsa_last_checked',
        'created_at',
        'updated_at'
    )

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user',
                'business_name',
                'slug',
                'description',
                'phone_number',
                'logo_url'
            )
        }),
        ('Location & Delivery', {
            'fields': (
                'location',
                'postcode',
                'delivery_radius_km'
            )
        }),
        ('Verification & Approval', {
            'fields': (
                'is_approved',
                'fsa_verified',
                'stripe_onboarding_complete'
            )
        }),
        ('FSA Integration', {
            'fields': (
                'fsa_establishment_id',
                'fsa_rating_value',
                'fsa_rating_date',
                'fsa_last_checked'
            )
        }),
        ('Payment & Commission', {
            'fields': (
                'stripe_account_id',
                'commission_rate',
                'min_order_value'
            )
        }),
        ('Business Details', {
            'fields': (
                'vat_number',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        })
    )

    def fsa_rating_display_admin(self, obj):
        if obj.fsa_rating_value:
            colors = {1: 'red', 2: 'orange',
                      3: 'yellow', 4: 'lightgreen', 5: 'green'}
            color = colors.get(obj.fsa_rating_value, 'gray')
            return format_html(
                '<span style="background-color: {}; padding: 3px 8px; border-radius: 3px;">{}/5</span>',
                color,
                obj.fsa_rating_value
            )
        return '-'
    fsa_rating_display_admin.short_description = 'FSA Rating'

    def stripe_status(self, obj):
        if obj.stripe_onboarding_complete:
            return format_html('<span style="color: green;">✓ Connected</span>')
        elif obj.stripe_account_id:
            return format_html('<span style="color: orange;">⚠ Pending</span>')
        return format_html('<span style="color: red;">✗ Not Connected</span>')
    stripe_status.short_description = 'Stripe Status'

    def commission_rate_display(self, obj):
        return f"{obj.commission_rate * 100:.0f}%"
    commission_rate_display.short_description = 'Commission'

    actions = ['approve_vendors', 'reject_vendors']

    def approve_vendors(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(
            request, f'{updated} vendor(s) approved successfully.')
    approve_vendors.short_description = 'Approve selected vendors'

    def reject_vendors(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} vendor(s) rejected.')
    reject_vendors.short_description = 'Reject selected vendors'
