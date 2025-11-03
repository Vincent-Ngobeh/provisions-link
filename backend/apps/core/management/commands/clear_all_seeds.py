# backend/apps/core/management/commands/clear_all_seeds.py

from django.core.management.base import BaseCommand
from django.db import connection

from apps.vendors.models import Vendor
from apps.products.models import Product, Category, Tag
from apps.orders.models import Order, OrderItem
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.core.models import User, Address


class Command(BaseCommand):
    help = 'Clear all seeded data from database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            confirm = input(
                '\n⚠️  WARNING: This will delete ALL seeded data!\n'
                'Type "yes" to continue: '
            )
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Operation cancelled'))
                return

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.WARNING('CLEARING ALL SEEDED DATA'))
        self.stdout.write('='*60 + '\n')

        # Delete in reverse dependency order
        models_to_clear = [
            ('Order Items', OrderItem),
            ('Orders', Order),
            ('Group Commitments', GroupCommitment),
            ('Buying Groups', BuyingGroup),
            ('Products', Product),
            ('Vendors', Vendor),
            ('Addresses', Address),
            ('Categories', Category),
            ('Tags', Tag),
        ]

        total_deleted = 0

        for model_name, model in models_to_clear:
            count = model.objects.count()
            if count > 0:
                model.objects.all().delete()
                self.stdout.write(f'  ✓ Deleted {count:4} {model_name}')
                total_deleted += count
            else:
                self.stdout.write(f'  - No {model_name} to delete')

        # Delete test users (vendors and buyers)
        test_users_count = User.objects.filter(
            email__endswith='@vendor.test'
        ).count() + User.objects.filter(
            email__endswith='@buyer.test'
        ).count()

        if test_users_count > 0:
            User.objects.filter(email__endswith='@vendor.test').delete()
            User.objects.filter(email__endswith='@buyer.test').delete()
            self.stdout.write(f'  ✓ Deleted {test_users_count:4} Test Users')
            total_deleted += test_users_count
        else:
            self.stdout.write(f'  - No Test Users to delete')

        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS(f'✅ CLEARED {total_deleted} TOTAL RECORDS')
        )
        self.stdout.write('='*60)
        self.stdout.write(
            '\nDatabase is now clean and ready for fresh seeds.\n')
        self.stdout.write('Run seeds in this order:')
        self.stdout.write('  1. python manage.py seed_categories')
        self.stdout.write('  2. python manage.py seed_users')
        self.stdout.write('  3. python manage.py seed_vendors')
        self.stdout.write('  4. python manage.py seed_products')
        self.stdout.write('  5. python manage.py seed_buying_groups')
        self.stdout.write('  6. python manage.py seed_orders')
        self.stdout.write('')
