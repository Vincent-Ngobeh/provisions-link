# backend/apps/buying_groups/management/commands/refresh_demo_groups.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, F
from datetime import timedelta
import random

from apps.buying_groups.models import BuyingGroup, GroupCommitment


class Command(BaseCommand):
    help = """Refresh demo buying groups intelligently.

    By default, only refreshes FAILED groups (didn't reach minimum quantity).
    This gives them a "second chance" while allowing successful groups to
    complete their natural lifecycle (orders created, payments captured).

    Completed and Active groups are left alone - they've already succeeded
    or are in the process of being fulfilled.
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--failed-only',
            action='store_true',
            default=True,
            help='Only refresh failed groups (default behavior)',
        )
        parser.add_argument(
            '--include-open-expired',
            action='store_true',
            help='Also refresh open groups that expired below minimum',
        )
        parser.add_argument(
            '--force-all',
            action='store_true',
            help='DANGEROUS: Refresh ALL demo groups regardless of status',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Specific number of days to extend (default: random 7-14)',
        )
        parser.add_argument(
            '--reset-progress',
            action='store_true',
            help='Reset current_quantity to ~30-50%% of target for refreshed groups',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be refreshed without making changes',
        )

    def handle(self, *args, **options):
        force_all = options['force_all']
        include_open_expired = options['include_open_expired']
        days_to_add = options['days']
        reset_progress = options['reset_progress']
        dry_run = options['dry_run']

        # Safety warning for force-all
        if force_all:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  WARNING: --force-all will refresh ALL groups including '
                    'completed ones!\n'
                    '    This may cause issues with order fulfillment.\n'
                )
            )

        # Build query for demo groups based on options
        demo_groups = BuyingGroup.objects.filter(
            area_name__startswith='[DEMO]'
        )

        if force_all:
            # Refresh everything (dangerous but available)
            pass
        elif include_open_expired:
            # Refresh failed groups AND open groups that expired below minimum
            demo_groups = demo_groups.filter(
                Q(status='failed') |
                Q(status='open', expires_at__lt=timezone.now(),
                  current_quantity__lt=F('min_quantity'))
            )
        else:
            # Default: only refresh failed groups
            demo_groups = demo_groups.filter(status='failed')

        if not demo_groups.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    '✅ No groups need refreshing!\n'
                    '   - Failed groups: None found\n'
                    '   - Completed/Active groups: Left alone (working as intended)'
                )
            )
            self._show_status_summary()
            return

        # Statistics before refresh
        total_count = demo_groups.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'\n🔍 DRY RUN: Would refresh {total_count} groups\n')
            )

        # Group by status for statistics
        status_counts = {}
        for group in demo_groups:
            status = group.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # Refresh each group
        refreshed_count = 0
        reset_count = 0

        self.stdout.write('\nRefreshing groups:\n')

        for group in demo_groups:
            # Calculate new expiry
            if days_to_add:
                extension_days = days_to_add
            else:
                # Random 7-14 days for variety
                extension_days = random.randint(7, 14)

            old_status = group.status
            old_quantity = group.current_quantity
            new_expiry = timezone.now() + timedelta(days=extension_days)

            # Calculate new progress if resetting
            new_quantity = old_quantity
            if reset_progress:
                # Reset to 30-50% of target for a fresh start
                progress_ratio = random.uniform(0.30, 0.50)
                new_quantity = int(group.target_quantity * progress_ratio)

            if not dry_run:
                # Update the group
                group.expires_at = new_expiry
                group.status = 'open'  # Reset to open
                group.last_update_at = timezone.now()

                if reset_progress:
                    group.current_quantity = new_quantity
                    reset_count += 1

                group.save(update_fields=[
                    'expires_at', 'status', 'last_update_at', 'current_quantity'
                ])

                # Also reset any cancelled commitments from the failed group
                # (Optional: could delete them instead)
                GroupCommitment.objects.filter(
                    group=group,
                    status='cancelled'
                ).update(status='pending')

            refreshed_count += 1

            # Calculate progress for display
            display_quantity = new_quantity if reset_progress else old_quantity
            progress_pct = (display_quantity / group.target_quantity *
                            100) if group.target_quantity > 0 else 0

            # Status change indicator
            status_change = f'{old_status} → open' if old_status != 'open' else 'open'
            quantity_change = ''
            if reset_progress and old_quantity != new_quantity:
                quantity_change = f' (reset from {old_quantity})'

            # Output with color coding
            self.stdout.write(
                f"  ♻️  {group.area_name[:28]:28} | "
                f"{group.product.name[:22]:22} | "
                f"{display_quantity:3}/{group.target_quantity:3} ({progress_pct:3.0f}%){quantity_change} | "
                f"{status_change} | +{extension_days}d → {new_expiry.strftime('%b %d')}"
            )

        # Summary
        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'🔍 DRY RUN: Would refresh {refreshed_count} demo groups'
                )
            )
            self.stdout.write('   Run without --dry-run to apply changes\n')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Refreshed {refreshed_count} demo groups'
                )
            )
            if reset_count > 0:
                self.stdout.write(f'   Reset progress on {reset_count} groups')

        # Show overall status summary
        self._show_status_summary()

        # Show next expiry
        if not dry_run:
            next_to_expire = BuyingGroup.objects.filter(
                area_name__startswith='[DEMO]',
                status='open'
            ).order_by('expires_at').first()

            if next_to_expire:
                time_until = next_to_expire.expires_at - timezone.now()
                days_until = time_until.days
                hours_until = int(time_until.total_seconds() // 3600) % 24
                self.stdout.write(
                    f'\n⏰ Next group expires in {days_until}d {hours_until}h '
                    f'({next_to_expire.expires_at.strftime("%b %d, %Y %H:%M")})'
                )

    def _show_status_summary(self):
        """Show summary of all demo groups by status."""
        self.stdout.write('\n📊 Demo Groups Status Summary:')

        demo_groups = BuyingGroup.objects.filter(
            area_name__startswith='[DEMO]')
        total = demo_groups.count()

        status_counts = {
            'open': demo_groups.filter(status='open').count(),
            'active': demo_groups.filter(status='active').count(),
            'completed': demo_groups.filter(status='completed').count(),
            'failed': demo_groups.filter(status='failed').count(),
        }

        self.stdout.write(f'   Total demo groups: {total}')
        self.stdout.write(
            f'   ├── Open (accepting commitments): {status_counts["open"]}')
        self.stdout.write(
            f'   ├── Active (processing orders):   {status_counts["active"]}')
        self.stdout.write(
            f'   ├── Completed (orders fulfilled): {status_counts["completed"]}')
        self.stdout.write(
            f'   └── Failed (below minimum):       {status_counts["failed"]}')

        # Show expired open groups (these will fail at next hourly check)
        expired_open = demo_groups.filter(
            status='open',
            expires_at__lt=timezone.now()
        ).count()

        if expired_open > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'\n   ⚠️  {expired_open} open groups have expired '
                    f'(will be processed at next hourly check)'
                )
            )
