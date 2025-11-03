# backend/apps/core/management/commands/seed_users.py

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.contrib.gis.geos import Point
from django.utils import timezone
from apps.core.models import User, Address, PrivacySettings


class Command(BaseCommand):
    help = 'Seed buyer users with addresses for portfolio demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing buyer users before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            # Only delete buyers (not vendor users)
            User.objects.filter(email__endswith='@buyer.test').delete()
            self.stdout.write(self.style.WARNING(
                'Cleared existing buyer users'))

        users_data = [
            {
                'email': 'james.chen@buyer.test',
                'username': 'jameschen',
                'password': 'buyer123',
                'first_name': 'James',
                'last_name': 'Chen',
                'phone_number': '07700 900123',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'James Chen',
                        'phone_number': '07700 900123',
                        'line1': '45 Redchurch Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E2 7DJ',
                        # Shoreditch - near multiple vendors
                        'location': Point(-0.0748, 51.5245),
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'James Chen',
                        'phone_number': '07700 900123',
                        'line1': '12 Columbia Road',
                        'line2': 'Flat 3',
                        'city': 'London',
                        'postcode': 'E2 7RG',
                        # Shoreditch residential
                        'location': Point(-0.0695, 51.5298),
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'sarah.williams@buyer.test',
                'username': 'sarahwilliams',
                'password': 'buyer123',
                'first_name': 'Sarah',
                'last_name': 'Williams',
                'phone_number': '07700 900234',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Sarah Williams',
                        'phone_number': '07700 900234',
                        'line1': '15 Exmouth Market',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'EC1R 4QD',
                        # Clerkenwell - near Smithfield
                        'location': Point(-0.1092, 51.5264),
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': False,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': False,
                },
            },
            {
                'email': 'michael.patel@buyer.test',
                'username': 'michaelpatel',
                'password': 'buyer123',
                'first_name': 'Michael',
                'last_name': 'Patel',
                'phone_number': '07700 900345',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Michael Patel',
                        'phone_number': '07700 900345',
                        'line1': '89 Brick Lane',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E1 6QL',
                        # Brick Lane - central location
                        'location': Point(-0.0719, 51.5213),
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'Michael Patel',
                        'phone_number': '07700 900345',
                        'line1': '23 Whitechapel Road',
                        'line2': 'Apartment 5B',
                        'city': 'London',
                        'postcode': 'E1 1DU',
                        'location': Point(-0.0646, 51.5156),  # Whitechapel
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': True,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'emma.johnson@buyer.test',
                'username': 'emmajohnson',
                'password': 'buyer123',
                'first_name': 'Emma',
                'last_name': 'Johnson',
                'phone_number': '07700 900456',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Emma Johnson',
                        'phone_number': '07700 900456',
                        'line1': '34 Long Lane',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'SE1 4PB',
                        # Borough - near Borough Market
                        'location': Point(-0.0928, 51.5018),
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'david.thompson@buyer.test',
                'username': 'davidthompson',
                'password': 'buyer123',
                'first_name': 'David',
                'last_name': 'Thompson',
                'phone_number': '07700 900567',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'David Thompson',
                        'phone_number': '07700 900567',
                        'line1': '78 Commercial Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E1 6LY',
                        'location': Point(-0.0755, 51.5184),  # Spitalfields
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'David Thompson',
                        'phone_number': '07700 900567',
                        'line1': '102 Bethnal Green Road',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E2 6DG',
                        'location': Point(-0.0682, 51.5252),  # Bethnal Green
                        'is_default': False,
                    },
                    {
                        'address_name': 'other',
                        'recipient_name': 'David Thompson',
                        'phone_number': '07700 900567',
                        'line1': '5 Mare Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E8 4RP',
                        'location': Point(-0.0558, 51.5364),  # Hackney
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': True,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'olivia.martinez@buyer.test',
                'username': 'oliviamartinez',
                'password': 'buyer123',
                'first_name': 'Olivia',
                'last_name': 'Martinez',
                'phone_number': '07700 900678',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Olivia Martinez',
                        'phone_number': '07700 900678',
                        'line1': '24 Monmouth Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'WC2H 9HB',
                        'location': Point(-0.1268, 51.5141),  # Covent Garden
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': False,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': False,
                },
            },
            {
                'email': 'robert.lee@buyer.test',
                'username': 'robertlee',
                'password': 'buyer123',
                'first_name': 'Robert',
                'last_name': 'Lee',
                'phone_number': '07700 900789',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Robert Lee',
                        'phone_number': '07700 900789',
                        'line1': '56 Great Eastern Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'EC2A 3QR',
                        'location': Point(-0.0849, 51.5243),  # Old Street
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'Robert Lee',
                        'phone_number': '07700 900789',
                        'line1': '17 Pitfield Street',
                        'line2': 'Flat 12',
                        'city': 'London',
                        'postcode': 'N1 6HB',
                        'location': Point(-0.0871, 51.5289),  # Hoxton
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'sophie.brown@buyer.test',
                'username': 'sophiebrown',
                'password': 'buyer123',
                'first_name': 'Sophie',
                'last_name': 'Brown',
                'phone_number': '07700 900890',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Sophie Brown',
                        'phone_number': '07700 900890',
                        'line1': '8 Greenwich Church Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'SE10 9BJ',
                        'location': Point(-0.0106, 51.4822),  # Greenwich
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': False,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': False,
                },
            },
            {
                'email': 'thomas.wilson@buyer.test',
                'username': 'thomaswilson',
                'password': 'buyer123',
                'first_name': 'Thomas',
                'last_name': 'Wilson',
                'phone_number': '07700 900901',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Thomas Wilson',
                        'phone_number': '07700 900901',
                        'line1': '42 Coldharbour Lane',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'SW9 8PS',
                        'location': Point(-0.1145, 51.4618),  # Brixton
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': True,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'jessica.garcia@buyer.test',
                'username': 'jessicagarcia',
                'password': 'buyer123',
                'first_name': 'Jessica',
                'last_name': 'Garcia',
                'phone_number': '07700 901012',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Jessica Garcia',
                        'phone_number': '07700 901012',
                        'line1': '91 Hackney Road',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E2 8ET',
                        'location': Point(-0.0699, 51.5307),  # Hackney
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'Jessica Garcia',
                        'phone_number': '07700 901012',
                        'line1': '33 Broadway Market',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E8 4PH',
                        'location': Point(-0.0635, 51.5362),  # Broadway Market
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'daniel.kumar@buyer.test',
                'username': 'danielkumar',
                'password': 'buyer123',
                'first_name': 'Daniel',
                'last_name': 'Kumar',
                'phone_number': '07700 901123',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Daniel Kumar',
                        'phone_number': '07700 901123',
                        'line1': '15 Old Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'EC1V 9HL',
                        'location': Point(-0.0904, 51.5256),  # Old Street area
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': False,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': False,
                },
            },
            {
                'email': 'anna.roberts@buyer.test',
                'username': 'annaroberts',
                'password': 'buyer123',
                'first_name': 'Anna',
                'last_name': 'Roberts',
                'phone_number': '07700 901234',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Anna Roberts',
                        'phone_number': '07700 901234',
                        'line1': '67 Long Lane',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'SE1 4PH',
                        'location': Point(-0.0933, 51.5021),  # Borough
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'Anna Roberts',
                        'phone_number': '07700 901234',
                        'line1': '28 Bermondsey Street',
                        'line2': 'Flat 4',
                        'city': 'London',
                        'postcode': 'SE1 3UD',
                        'location': Point(-0.0784, 51.4979),  # Bermondsey
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': True,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'william.davis@buyer.test',
                'username': 'williamdavis',
                'password': 'buyer123',
                'first_name': 'William',
                'last_name': 'Davis',
                'phone_number': '07700 901345',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'William Davis',
                        'phone_number': '07700 901345',
                        'line1': '22 Kingsland Road',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E2 8DA',
                        # Shoreditch/Hoxton border
                        'location': Point(-0.0765, 51.5296),
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': False,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': False,
                },
            },
            {
                'email': 'lucy.anderson@buyer.test',
                'username': 'lucyanderson',
                'password': 'buyer123',
                'first_name': 'Lucy',
                'last_name': 'Anderson',
                'phone_number': '07700 901456',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Lucy Anderson',
                        'phone_number': '07700 901456',
                        'line1': '5 Neal Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'WC2H 9PU',
                        'location': Point(-0.1276, 51.5147),  # Covent Garden
                        'is_default': True,
                    },
                    {
                        'address_name': 'home',
                        'recipient_name': 'Lucy Anderson',
                        'phone_number': '07700 901456',
                        'line1': '11 Drury Lane',
                        'line2': 'Apartment 8',
                        'city': 'London',
                        'postcode': 'WC2B 5RJ',
                        # Covent Garden residential
                        'location': Point(-0.1207, 51.5134),
                        'is_default': False,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': False,
                    'analytics_tracking': True,
                },
            },
            {
                'email': 'chris.taylor@buyer.test',
                'username': 'christaylor',
                'password': 'buyer123',
                'first_name': 'Chris',
                'last_name': 'Taylor',
                'phone_number': '07700 901567',
                'addresses': [
                    {
                        'address_name': 'work',
                        'recipient_name': 'Chris Taylor',
                        'phone_number': '07700 901567',
                        'line1': '34 Hanbury Street',
                        'line2': '',
                        'city': 'London',
                        'postcode': 'E1 6QR',
                        'location': Point(-0.0723, 51.5199),  # Spitalfields
                        'is_default': True,
                    },
                ],
                'privacy': {
                    'marketing_emails': True,
                    'order_updates': True,
                    'data_sharing': True,
                    'analytics_tracking': True,
                },
            },
        ]

        created_users = 0
        created_addresses = 0

        for data in users_data:
            # Extract nested data
            addresses_data = data.pop('addresses')
            privacy_data = data.pop('privacy')
            password = data.pop('password')

            # Create or get user
            user, user_created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'username': data['username'],
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'phone_number': data.get('phone_number', ''),
                }
            )

            if user_created:
                user.set_password(password)
                user.save()
                created_users += 1

                # Create privacy settings
                PrivacySettings.objects.get_or_create(
                    user=user,
                    defaults=privacy_data
                )

                # Create addresses
                for addr_data in addresses_data:
                    address, addr_created = Address.objects.get_or_create(
                        user=user,
                        address_name=addr_data['address_name'],
                        defaults=addr_data
                    )
                    if addr_created:
                        created_addresses += 1

                # Output user info
                addr_count = len(addresses_data)
                privacy_status = ' Private' if not privacy_data['marketing_emails'] else ' Marketing OK'

                self.stdout.write(
                    f"  ✓ {user.first_name} {user.last_name} | {addr_count} address{'es' if addr_count > 1 else ''} | {privacy_status}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n Created {created_users} buyer users with {created_addresses} addresses')
        )

        # Summary statistics
        total_users = User.objects.filter(
            email__endswith='@buyer.test').count()
        total_addresses = Address.objects.filter(
            user__email__endswith='@buyer.test').count()
        users_with_multiple_addresses = User.objects.filter(
            email__endswith='@buyer.test',
            addresses__isnull=False
        ).annotate(
            addr_count=Count('addresses')
        ).filter(addr_count__gt=1).count()

        self.stdout.write('\nBuyer Statistics:')
        self.stdout.write(f'  Total buyers: {total_users}')
        self.stdout.write(f'  Total addresses: {total_addresses}')
        self.stdout.write(
            f'  Buyers with multiple addresses: {users_with_multiple_addresses}')
        self.stdout.write(f'\nTest login: james.chen@buyer.test / buyer123')
