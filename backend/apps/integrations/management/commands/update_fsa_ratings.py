# backend/apps/integrations/management/commands/update_fsa_ratings.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.vendors.models import Vendor
from apps.integrations.services.fsa_service import FSAService


class Command(BaseCommand):
    help = 'Manually update FSA ratings for all vendors with FSA establishment IDs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vendor-id',
            type=int,
            help='Update only a specific vendor by ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if recently checked (ignore cache)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each vendor',
        )

    def handle(self, *args, **options):
        vendor_id = options.get('vendor_id')
        force = options.get('force', False)
        verbose = options.get('verbose', False)

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('FSA RATING UPDATE'))
        self.stdout.write('='*60)
        self.stdout.write(
            f'Started: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write(f'Force update: {force}')
        self.stdout.write('='*60 + '\n')

        # Get vendors to update
        if vendor_id:
            vendors = Vendor.objects.filter(id=vendor_id)
            if not vendors.exists():
                self.stdout.write(
                    self.style.ERROR(f'✗ Vendor with ID {vendor_id} not found')
                )
                return
        else:
            # Get all vendors with FSA establishment IDs
            vendors = Vendor.objects.exclude(fsa_establishment_id=None)

        total_vendors = vendors.count()
        self.stdout.write(f'Found {total_vendors} vendors with FSA IDs\n')

        if total_vendors == 0:
            self.stdout.write(
                self.style.WARNING(
                    'No vendors with FSA establishment IDs found.')
            )
            self.stdout.write(
                'Add FSA IDs to vendors first, then run this command.\n')
            return

        # Initialize FSA service
        fsa_service = FSAService()

        # Track results
        updated_count = 0
        skipped_count = 0
        error_count = 0
        results = []

        # Update each vendor
        for vendor in vendors:
            if verbose:
                self.stdout.write(f'\n{"─"*60}')
                self.stdout.write(f'Vendor: {vendor.business_name}')
                self.stdout.write(f'FSA ID: {vendor.fsa_establishment_id}')
                self.stdout.write(
                    f'Last checked: {vendor.fsa_last_checked or "Never"}')

            # Call FSA service to update rating
            result = fsa_service.update_vendor_rating(
                vendor_id=vendor.id,
                force=force
            )

            if result.success:
                rating_data = result.data

                # Check if actually updated or skipped due to cache
                if rating_data.get('updated'):
                    updated_count += 1
                    status = '✓'
                    message = f"Updated: {rating_data.get('rating', 'N/A')}★"
                    style = self.style.SUCCESS
                else:
                    skipped_count += 1
                    status = '○'
                    message = f"Cached: {rating_data.get('rating', 'N/A')}★ (checked recently)"
                    style = self.style.WARNING

                results.append({
                    'vendor': vendor.business_name,
                    'status': status,
                    'message': message,
                    'rating': rating_data.get('rating'),
                    'date': rating_data.get('rating_date'),
                })

                if verbose:
                    self.stdout.write(style(f'{status} {message}'))
                    if rating_data.get('rating_date'):
                        self.stdout.write(
                            f'  Rating date: {rating_data["rating_date"]}')
                    if rating_data.get('business_name'):
                        self.stdout.write(
                            f'  FSA business name: {rating_data["business_name"]}')
                else:
                    self.stdout.write(
                        style(
                            f'{status} {vendor.business_name[:40]:40} | {message}')
                    )

            else:
                error_count += 1
                status = '✗'
                message = f"Error: {result.error}"
                results.append({
                    'vendor': vendor.business_name,
                    'status': status,
                    'message': message,
                    'rating': None,
                    'date': None,
                })

                if verbose:
                    self.stdout.write(self.style.ERROR(f'{status} {message}'))
                    self.stdout.write(f'  Error code: {result.error_code}')
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'{status} {vendor.business_name[:40]:40} | {message[:40]}'
                        )
                    )

        # Check for vendors without FSA IDs
        vendors_without_fsa = Vendor.objects.filter(
            fsa_establishment_id=None).count()

        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('UPDATE SUMMARY'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total vendors processed: {total_vendors}')
        self.stdout.write(f'  ✓ Updated: {updated_count}')
        self.stdout.write(f'  ○ Skipped (cached): {skipped_count}')
        self.stdout.write(f'  ✗ Errors: {error_count}')

        if vendors_without_fsa > 0:
            self.stdout.write(
                f'\n⏳ Vendors pending FSA ID: {vendors_without_fsa}')

            if verbose:
                pending_vendors = Vendor.objects.filter(
                    fsa_establishment_id=None)
                self.stdout.write('\nVendors without FSA IDs:')
                for vendor in pending_vendors[:5]:  # Show first 5
                    self.stdout.write(f'  • {vendor.business_name}')
                if vendors_without_fsa > 5:
                    self.stdout.write(
                        f'  ... and {vendors_without_fsa - 5} more')

        # Rating distribution
        if updated_count > 0 or skipped_count > 0:
            self.stdout.write('\n' + '─'*60)
            self.stdout.write('FSA RATING DISTRIBUTION')
            self.stdout.write('─'*60)

            rating_counts = {}
            for r in results:
                if r['rating'] is not None:
                    rating_counts[r['rating']] = rating_counts.get(
                        r['rating'], 0) + 1

            for rating in sorted(rating_counts.keys(), reverse=True):
                stars = '★' * int(rating) if rating else 'N/A'
                count = rating_counts[rating]
                bar = '█' * count
                self.stdout.write(
                    f'  {rating}★ {stars:5} | {bar} ({count} vendors)')

        self.stdout.write('\n' + '='*60)

        if error_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'⚠️  Completed with {error_count} errors'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ All updates completed successfully!')
            )

        self.stdout.write(
            f'Finished: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.stdout.write('='*60 + '\n')

        # Tips
        if not force and skipped_count > 0:
            self.stdout.write(
                '💡 TIP: Use --force to update even recently checked vendors')

        if not verbose and (updated_count > 0 or error_count > 0):
            self.stdout.write('💡 TIP: Use --verbose for detailed output')

        self.stdout.write('')
