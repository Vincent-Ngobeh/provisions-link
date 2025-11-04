"""
Management command to create real test Stripe Connect accounts for vendors.
"""
from django.core.management.base import BaseCommand
from django.db import models
from django.conf import settings
from apps.vendors.models import Vendor
import stripe


class Command(BaseCommand):
    help = 'Create real test Stripe Connect accounts for vendors in test mode'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vendor-id',
            type=int,
            help='Specific vendor ID to setup (optional)',
        )

    def handle(self, *args, **options):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        # Check if we're in test mode
        if stripe.api_key.startswith('sk_live_'):
            self.stdout.write(self.style.ERROR(
                'ERROR: Cannot run this command in live mode!'
            ))
            return

        self.stdout.write(self.style.SUCCESS('Running in TEST mode'))

        # Get vendors to setup
        if options['vendor_id']:
            vendors = Vendor.objects.filter(id=options['vendor_id'])
        else:
            # Get vendors with placeholder or no Stripe accounts
            vendors = Vendor.objects.filter(
                models.Q(stripe_account_id__isnull=True) |
                models.Q(stripe_account_id='') |
                models.Q(stripe_account_id__icontains='test')
            )

        for vendor in vendors:
            try:
                self.stdout.write(
                    f'\nProcessing vendor: {vendor.business_name} (ID: {vendor.id})'
                )

                # Create a test Express account
                account = stripe.Account.create(
                    type='express',
                    country='GB',
                    email=vendor.user.email,
                    capabilities={
                        'card_payments': {'requested': True},
                        'transfers': {'requested': True}
                    },
                    business_type='company',
                    company={
                        'name': vendor.business_name,
                        'phone': vendor.phone_number or None,
                    },
                    metadata={
                        'vendor_id': str(vendor.id),
                        'platform': 'provisions_link',
                        'test_account': 'true'
                    }
                )

                # Update vendor with real test account
                vendor.stripe_account_id = account.id
                # They still need to complete onboarding
                vendor.stripe_onboarding_complete = False
                vendor.save(update_fields=[
                    'stripe_account_id',
                    'stripe_onboarding_complete'
                ])

                self.stdout.write(self.style.SUCCESS(
                    f'✓ Created test account: {account.id}'
                ))

                # Generate onboarding link
                account_link = stripe.AccountLink.create(
                    account=account.id,
                    refresh_url=f'{settings.FRONTEND_URL}/vendor/onboarding/refresh',
                    return_url=f'{settings.FRONTEND_URL}/vendor/onboarding/complete',
                    type='account_onboarding',
                )

                self.stdout.write(self.style.WARNING(
                    f'  Onboarding URL: {account_link.url}'
                ))

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'✗ Failed to create account for {vendor.business_name}: {e}'
                ))
