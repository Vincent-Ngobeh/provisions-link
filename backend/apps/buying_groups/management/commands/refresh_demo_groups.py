# backend/apps/buying_groups/management/commands/refresh_demo_groups.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F
from datetime import timedelta
import random

from apps.buying_groups.models import BuyingGroup


class Command(BaseCommand):
    help = 'Refresh demo buying groups by extending expiry dates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Refresh all demo groups, not just expired ones',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Specific number of days to extend (default: random 7-14)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be refreshed without making changes',
        )

    def handle(self, *args, **options):
        refresh_all = options['all']
        days_to_add = options['days']
        dry_run = options['dry_run']

        # Build query for demo groups
        demo_groups = BuyingGroup.objects.filter(
            area_name__startswith='[DEMO]'
        )

        # Filter by expiry unless --all flag
        if not refresh_all:
            demo_groups = demo_groups.filter(expires_at__lt=timezone.now())

        if not demo_groups.exists():
            self.stdout.write(
                self.style.SUCCESS('All demo groups are up to date!')
            )
            return

        # Statistics before refresh
        total_count = demo_groups.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would refresh {total_count} groups')
            )

        # Group by status for statistics
        status_counts = {}
        for group in demo_groups:
            status = group.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # Refresh each group
        refreshed_count = 0

        for group in demo_groups:
            # Calculate new expiry
            if days_to_add:
                extension_days = days_to_add
            else:
                # Random 7-14 days for variety
                extension_days = random.randint(7, 14)

            old_expiry = group.expires_at
            new_expiry = timezone.now() + timedelta(days=extension_days)

            if not dry_run:
                group.expires_at = new_expiry
                group.last_update_at = timezone.now()
                group.save(update_fields=['expires_at', 'last_update_at'])

            refreshed_count += 1

            # Calculate progress
            progress_pct = (group.current_quantity / group.target_quantity *
                            100) if group.target_quantity > 0 else 0

            # Status icon
            status_icon = {
                'open': '[OPEN]',
                'active': '[ACTIVE]',
                'failed': '[FAILED]',
                'completed': '[COMPLETED]',
            }.get(group.status, '[UNKNOWN]')

            # Output
            self.stdout.write(
                f"  {status_icon} {group.area_name[:30]:30} | "
                f"{group.product.name[:25]:25} | "
                f"{group.current_quantity:3}/{group.target_quantity:3} ({progress_pct:.0f}%) | "
                f"+{extension_days}d -> {new_expiry.strftime('%b %d')}"
            )

        # Summary
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\nDRY RUN: Would refresh {refreshed_count} demo groups'
                )
            )
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nRefreshed {refreshed_count} demo groups'
                )
            )

        # Statistics
        self.stdout.write('\nRefresh Summary:')
        self.stdout.write(
            f'  Total demo groups in database: {BuyingGroup.objects.filter(area_name__startswith="[DEMO]").count()}')
        self.stdout.write(f'  Groups refreshed: {refreshed_count}')

        if status_counts:
            self.stdout.write(f'\nStatus Distribution (refreshed groups):')
            for status, count in sorted(status_counts.items()):
                self.stdout.write(f'  {status}: {count}')

        # Show next expiry
        if not dry_run:
            next_to_expire = BuyingGroup.objects.filter(
                area_name__startswith='[DEMO]'
            ).order_by('expires_at').first()

            if next_to_expire:
                days_until = (next_to_expire.expires_at - timezone.now()).days
                self.stdout.write(
                    f'\nNext group expires in {days_until} days ({next_to_expire.expires_at.strftime("%b %d, %Y")})')
