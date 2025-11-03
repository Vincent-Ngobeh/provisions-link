# backend/apps/vendors/management/commands/seed_vendors.py

from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils import timezone
from decimal import Decimal
from apps.vendors.models import Vendor
from apps.core.models import User


class Command(BaseCommand):
    help = 'Seed vendors with realistic FSA integration for portfolio demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing vendors before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            Vendor.objects.all().delete()
            # Delete vendor users
            User.objects.filter(email__endswith='@vendor.test').delete()
            self.stdout.write(self.style.WARNING('Cleared existing vendors'))

        vendors_data = [
            # ==========================================
            # HIGH-QUALITY VENDORS (Real 5★ FSA Ratings)
            # These vendors have real FSA IDs that will be verified automatically
            # ==========================================
            {
                'email': 'borough.market@vendor.test',
                'username': 'boroughmarket',
                'password': 'vendor123',
                'first_name': 'Borough',
                'last_name': 'Manager',
                'business_name': 'Borough Market Organics',
                'description': 'Premium organic produce supplier serving London restaurants since 1998. Specialising in seasonal British vegetables, heritage varieties, and artisan products. Direct relationships with over 50 local farms.',
                'phone_number': '020 7407 1002',
                'postcode': 'SE1 9AL',
                'location': Point(-0.0906, 51.5055),
                'delivery_radius_km': 25,
                'min_order_value': Decimal('75.00'),
                'vat_number': 'GB123456789',
                'commission_rate': Decimal('0.08'),
                'is_approved': True,
                # Real FSA Integration - 5★ Rating
                'fsa_establishment_id': '1692230',  # Real: Akara, SE1
                'fsa_rating_value': None,  # Will auto-populate as 5★
                'fsa_rating_date': None,  # Will auto-populate
                'fsa_last_checked': None,  # Will auto-populate
                'fsa_verified': False,  # Will become True after Celery verification
                # Stripe (demo setup)
                'stripe_account_id': 'acct_test_borough_001',
                'stripe_onboarding_complete': True,
            },
            {
                'email': 'smithfield.meats@vendor.test',
                'username': 'smithfieldmeats',
                'password': 'vendor123',
                'first_name': 'John',
                'last_name': 'Smith',
                'business_name': 'Smithfield Premium Meats',
                'description': 'Traditional butchers and meat wholesaler located in historic Smithfield Market. Supplying high-quality British beef, lamb, and poultry to restaurants across the capital. Halal-certified options available.',
                'phone_number': '020 7248 3151',
                'postcode': 'EC1A 9PS',
                'location': Point(-0.1013, 51.5194),
                'delivery_radius_km': 20,
                'min_order_value': Decimal('100.00'),
                'vat_number': 'GB234567890',
                'commission_rate': Decimal('0.09'),
                'is_approved': True,
                # Real FSA Integration - 5★ Rating
                'fsa_establishment_id': '1093754',  # Real: Aramark @, EC1
                'fsa_rating_value': None,  # Will auto-populate as 5★
                'fsa_rating_date': None,  # Will auto-populate
                'fsa_last_checked': None,  # Will auto-populate
                'fsa_verified': False,  # Will become True after Celery verification
                # Stripe (demo setup)
                'stripe_account_id': 'acct_test_smithfield_002',
                'stripe_onboarding_complete': True,
            },
            {
                'email': 'spitalfields.dairy@vendor.test',
                'username': 'spitalfieldsdairy',
                'password': 'vendor123',
                'first_name': 'Sarah',
                'last_name': 'Williams',
                'business_name': 'Spitalfields Artisan Dairy',
                'description': 'Artisan dairy products from small British farms. Free-range eggs, farmhouse cheeses, organic milk, and cultured butter. Winner of 3 Great Taste Awards. Same-day delivery available for East London.',
                'phone_number': '020 7377 8963',
                'postcode': 'E1 6EA',
                'location': Point(-0.0751, 51.5188),
                'delivery_radius_km': 15,
                'min_order_value': Decimal('50.00'),
                'vat_number': 'GB345678901',
                'commission_rate': Decimal('0.10'),
                'is_approved': True,
                # Real FSA Integration - 5★ Rating
                'fsa_establishment_id': '98824',  # Real: A&O Shearman LLP, E1
                'fsa_rating_value': None,  # Will auto-populate as 5★
                'fsa_rating_date': None,  # Will auto-populate
                'fsa_last_checked': None,  # Will auto-populate
                'fsa_verified': False,  # Will become True after Celery verification
                # Stripe (demo setup)
                'stripe_account_id': 'acct_test_spitalfields_003',
                'stripe_onboarding_complete': True,
            },
            {
                'email': 'covent.bakery@vendor.test',
                'username': 'coventbakery',
                'password': 'vendor123',
                'first_name': 'Pierre',
                'last_name': 'Dubois',
                'business_name': 'Covent Garden Artisan Bakery',
                'description': 'French-inspired wholesale bakery producing sourdough breads, pastries, and viennoiserie. Freshly baked daily using traditional methods and organic flour. Early morning delivery available.',
                'phone_number': '020 7836 4521',
                'postcode': 'WC2E 8RF',
                'location': Point(-0.1224, 51.5117),
                'delivery_radius_km': 18,
                'min_order_value': Decimal('60.00'),
                'vat_number': 'GB456789012',
                'commission_rate': Decimal('0.10'),
                'is_approved': True,
                # Real FSA Integration - 5★ Rating
                'fsa_establishment_id': '1623981',  # Real: Amorino, SE1
                'fsa_rating_value': None,  # Will auto-populate as 5★
                'fsa_rating_date': None,  # Will auto-populate
                'fsa_last_checked': None,  # Will auto-populate
                'fsa_verified': False,  # Will become True after Celery verification
                # Stripe (demo setup)
                'stripe_account_id': 'acct_test_covent_004',
                'stripe_onboarding_complete': True,
            },

            # ==========================================
            # GOOD VENDOR (Real 4★ FSA Rating)
            # Demonstrates handling of non-perfect ratings
            # ==========================================
            {
                'email': 'shoreditch.seafood@vendor.test',
                'username': 'shoreditchseafood',
                'password': 'vendor123',
                'first_name': 'Michael',
                'last_name': 'Chen',
                'business_name': 'Shoreditch Fresh Seafood',
                'description': 'Day boat fish and premium seafood delivered fresh from Cornish and Scottish ports. Sustainable sourcing, MSC certified where possible. Daily catch updates via WhatsApp. Perfect for modern seafood restaurants.',
                'phone_number': '020 7739 4287',
                'postcode': 'E2 7RH',
                'location': Point(-0.0741, 51.5265),
                'delivery_radius_km': 12,
                'min_order_value': Decimal('120.00'),
                'vat_number': 'GB567890123',
                'commission_rate': Decimal('0.09'),
                'is_approved': True,
                # Real FSA Integration - 4★ Rating
                'fsa_establishment_id': '151051',  # Real: Lawrence Bros Billingsgate, E14
                'fsa_rating_value': None,  # Will auto-populate as 4★
                'fsa_rating_date': None,  # Will auto-populate
                'fsa_last_checked': None,  # Will auto-populate
                'fsa_verified': False,  # Will become True after Celery verification
                # Stripe (incomplete - shows onboarding flow)
                'stripe_account_id': 'acct_test_shoreditch_005',
                'stripe_onboarding_complete': False,
            },

            # ==========================================
            # PENDING FSA VERIFICATION VENDORS
            # These vendors simulate new registrations or businesses without FSA IDs
            # Demonstrates proper null state handling and user onboarding flow
            # ==========================================
            {
                'email': 'hackney.provisions@vendor.test',
                'username': 'hackneyprovisions',
                'password': 'vendor123',
                'first_name': 'Emma',
                'last_name': 'Thompson',
                'business_name': 'Hackney Provisions Co',
                'description': 'Specialty food wholesaler focusing on international ingredients and pantry staples. Mediterranean oils, Asian condiments, premium spices, and hard-to-find ingredients. Recently expanded to include British artisan products.',
                'phone_number': '020 8985 2341',
                'postcode': 'E8 2LY',
                'location': Point(-0.0553, 51.5434),
                'delivery_radius_km': 20,
                'min_order_value': Decimal('80.00'),
                'vat_number': '',
                'commission_rate': Decimal('0.12'),
                'is_approved': True,
                # FSA Pending - Vendor hasn't provided FSA ID yet
                'fsa_establishment_id': None,  # Pending verification
                'fsa_rating_value': None,
                'fsa_rating_date': None,
                'fsa_last_checked': None,
                'fsa_verified': False,
                # Stripe (incomplete - realistic scenario)
                'stripe_account_id': 'acct_test_hackney_006',
                'stripe_onboarding_complete': False,
            },
            {
                'email': 'greenwich.greens@vendor.test',
                'username': 'greenwichgreens',
                'password': 'vendor123',
                'first_name': 'David',
                'last_name': 'Green',
                'business_name': 'Greenwich Urban Greens',
                'description': 'Urban vertical farm producing microgreens, salad leaves, and fresh herbs year-round. Zero food miles, harvested to order within 24 hours. Perfect for restaurants seeking ultra-fresh, sustainable produce.',
                'phone_number': '020 8858 7652',
                'postcode': 'SE10 9GB',
                'location': Point(-0.0077, 51.4825),
                'delivery_radius_km': 15,
                'min_order_value': Decimal('40.00'),
                'vat_number': '',
                'commission_rate': Decimal('0.15'),
                'is_approved': False,  # New vendor pending approval
                # FSA Pending - New vendor still in onboarding
                'fsa_establishment_id': None,  # Pending verification
                'fsa_rating_value': None,
                'fsa_rating_date': None,
                'fsa_last_checked': None,
                'fsa_verified': False,
                # Stripe (not started - realistic new vendor)
                # CHANGE: Use None instead of empty string
                'stripe_account_id': None,
                'stripe_onboarding_complete': False,
            },
            {
                'email': 'brixton.butcher@vendor.test',
                'username': 'brixtonbutcher',
                'password': 'vendor123',
                'first_name': 'Marcus',
                'last_name': 'Johnson',
                'business_name': 'Brixton Traditional Butchers',
                'description': 'Family-run butchery serving South London for 40 years. Specialising in Caribbean-style cuts and marinades. Grass-fed beef, free-range chicken, and artisan sausages. Recent expansion into restaurant wholesale.',
                'phone_number': '020 7274 3892',
                'postcode': 'SW9 8PS',
                'location': Point(-0.1149, 51.4613),
                'delivery_radius_km': 10,
                'min_order_value': Decimal('90.00'),
                'vat_number': '',
                'commission_rate': Decimal('0.15'),
                'is_approved': False,  # New vendor pending approval
                # FSA Pending - Vendor is being onboarded
                'fsa_establishment_id': None,  # Pending verification
                'fsa_rating_value': None,
                'fsa_rating_date': None,
                'fsa_last_checked': None,
                'fsa_verified': False,
                # Stripe (not started - realistic new vendor)
                # CHANGE: Use None instead of empty string
                'stripe_account_id': None,
                'stripe_onboarding_complete': False,
            },
        ]

        created_count = 0

        for data in vendors_data:
            # Extract user data
            user_data = {
                'email': data.pop('email'),
                'username': data.pop('username'),
                'password': data.pop('password'),
                'first_name': data.pop('first_name'),
                'last_name': data.pop('last_name'),
            }

            # Create or get user
            user, user_created = User.objects.get_or_create(
                email=user_data['email'],
                defaults={
                    'username': user_data['username'],
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                }
            )

            if user_created:
                user.set_password(user_data['password'])
                user.save()

            # Create vendor if doesn't exist
            vendor, vendor_created = Vendor.objects.get_or_create(
                user=user,
                defaults=data
            )

            if vendor_created:
                created_count += 1

                # Status indicators
                approval_status = '✓ Approved' if vendor.is_approved else '⏳ Pending'

                # FSA status
                if vendor.fsa_establishment_id:
                    fsa_status = f'FSA {vendor.fsa_establishment_id[:6]}... (real)'
                else:
                    fsa_status = 'FSA Pending'

                # Stripe status
                stripe_status = '✓ Stripe' if vendor.stripe_onboarding_complete else '⏳ Stripe'

                self.stdout.write(
                    f"  {approval_status:12} | {fsa_status:25} | {stripe_status:10} | {vendor.business_name}"
                )

        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Created {created_count} vendors')
        )

        # Summary statistics
        total = Vendor.objects.count()
        approved = Vendor.objects.filter(is_approved=True).count()
        fsa_with_id = Vendor.objects.exclude(fsa_establishment_id=None).count()
        fsa_pending = Vendor.objects.filter(fsa_establishment_id=None).count()
        stripe_complete = Vendor.objects.filter(
            stripe_onboarding_complete=True).count()

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('VENDOR STATISTICS'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total vendors: {total}')
        self.stdout.write(f'Approved: {approved}')
        self.stdout.write(f'\nFSA Integration:')
        self.stdout.write(f'  With FSA ID (will be verified): {fsa_with_id}')
        self.stdout.write(f'  Pending FSA ID: {fsa_pending}')
        self.stdout.write(f'\nStripe Integration:')
        self.stdout.write(f'  Onboarding complete: {stripe_complete}')

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('FSA VERIFICATION SETUP'))
        self.stdout.write('='*60)
        self.stdout.write(
            'Real FSA IDs will be verified automatically by Celery.')
        self.stdout.write('\nTo trigger immediate verification:')
        self.stdout.write(
            '  docker compose exec backend python manage.py update_fsa_ratings')
        self.stdout.write('\nOr wait for automatic weekly updates.')

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('PORTFOLIO PRESENTATION'))
        self.stdout.write('='*60)
        self.stdout.write('This setup demonstrates:')
        self.stdout.write('  ✓ Real FSA API integration (5 vendors)')
        self.stdout.write('  ✓ Pending/null state handling (3 vendors)')
        self.stdout.write('  ✓ Rating variety (5★ and 4★)')
        self.stdout.write('  ✓ Realistic London marketplace data')
        self.stdout.write('  ✓ Professional approach to third-party APIs')

        self.stdout.write(f'\n' + '='*60)
        self.stdout.write(
            f'Test login: borough.market@vendor.test / vendor123')
        self.stdout.write('='*60 + '\n')
