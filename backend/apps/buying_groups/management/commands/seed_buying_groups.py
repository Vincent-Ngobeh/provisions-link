from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.db.models import Q, F
from decimal import Decimal
from datetime import timedelta
import random

from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.products.models import Product
from apps.core.models import User


class Command(BaseCommand):
    help = 'Seed buying groups with commitments for portfolio demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing buying groups before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            BuyingGroup.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                'Cleared existing buying groups'))

        # Get all products and buyers
        products = list(Product.objects.filter(is_active=True))
        buyers = list(User.objects.filter(email__endswith='@buyer.test'))

        if not products:
            self.stdout.write(self.style.ERROR(
                'No products found. Run seed_products first.'))
            return

        if not buyers:
            self.stdout.write(self.style.ERROR(
                'No buyers found. Run seed_users first.'))
            return

        # London locations for group centers (neighborhoods with good buyer coverage)
        london_locations = [
            {'name': '[DEMO] Shoreditch',
                'point': Point(-0.0748, 51.5245), 'radius': 5},
            {'name': '[DEMO] Spitalfields',
                'point': Point(-0.0755, 51.5184), 'radius': 4},
            {'name': '[DEMO] Brick Lane Area',
                'point': Point(-0.0719, 51.5213), 'radius': 3},
            {'name': '[DEMO] Borough Market',
                'point': Point(-0.0906, 51.5055), 'radius': 6},
            {'name': '[DEMO] Clerkenwell',
                'point': Point(-0.1092, 51.5264), 'radius': 5},
            {'name': '[DEMO] Old Street',
                'point': Point(-0.0904, 51.5256), 'radius': 4},
            {'name': '[DEMO] Hackney Central',
                'point': Point(-0.0558, 51.5364), 'radius': 5},
            {'name': '[DEMO] Bethnal Green',
                'point': Point(-0.0682, 51.5252), 'radius': 4},
            {'name': '[DEMO] Covent Garden',
                'point': Point(-0.1268, 51.5141), 'radius': 5},
            {'name': '[DEMO] Hoxton',
                'point': Point(-0.0871, 51.5289), 'radius': 3},
            {'name': '[DEMO] Whitechapel',
                'point': Point(-0.0646, 51.5156), 'radius': 5},
            {'name': '[DEMO] Bermondsey',
                'point': Point(-0.0784, 51.4979), 'radius': 6},
            {'name': '[DEMO] Greenwich',
                'point': Point(-0.0106, 51.4822), 'radius': 7},
            {'name': '[DEMO] Brixton',
                'point': Point(-0.1145, 51.4618), 'radius': 5},
            {'name': '[DEMO] Camden',
                'point': Point(-0.1426, 51.5390), 'radius': 6},
        ]

        # Buying group templates with varied progress levels
        group_templates = [
            # Near completion (80-95%) - 5 groups
            {'progress_level': 0.90, 'target': 100,
                'discount': 15, 'days_until_expiry': 3},
            {'progress_level': 0.85, 'target': 80,
                'discount': 12, 'days_until_expiry': 4},
            {'progress_level': 0.95, 'target': 120,
                'discount': 20, 'days_until_expiry': 5},
            {'progress_level': 0.88, 'target': 60,
                'discount': 10, 'days_until_expiry': 3},
            {'progress_level': 0.92, 'target': 150,
                'discount': 18, 'days_until_expiry': 6},

            # Moderate progress (50-70%) - 6 groups
            {'progress_level': 0.65, 'target': 80,
                'discount': 15, 'days_until_expiry': 7},
            {'progress_level': 0.55, 'target': 100,
                'discount': 12, 'days_until_expiry': 8},
            {'progress_level': 0.70, 'target': 90,
                'discount': 15, 'days_until_expiry': 9},
            {'progress_level': 0.60, 'target': 70,
                'discount': 10, 'days_until_expiry': 7},
            {'progress_level': 0.68, 'target': 110,
                'discount': 18, 'days_until_expiry': 10},
            {'progress_level': 0.58, 'target': 85,
                'discount': 12, 'days_until_expiry': 8},

            # Just started (20-40%) - 5 groups
            {'progress_level': 0.30, 'target': 100,
                'discount': 15, 'days_until_expiry': 12},
            {'progress_level': 0.25, 'target': 80,
                'discount': 10, 'days_until_expiry': 14},
            {'progress_level': 0.35, 'target': 120,
                'discount': 20, 'days_until_expiry': 11},
            {'progress_level': 0.28, 'target': 90,
                'discount': 12, 'days_until_expiry': 13},
            {'progress_level': 0.38, 'target': 75,
                'discount': 15, 'days_until_expiry': 10},

            # Completed (100%+) - 2 groups for 'active' status testing
            {'progress_level': 1.05, 'target': 60, 'discount': 15,
                'days_until_expiry': 2, 'status': 'active'},
            {'progress_level': 1.10, 'target': 80, 'discount': 20,
                'days_until_expiry': 3, 'status': 'active'},
        ]

        created_groups = 0
        created_commitments = 0

        # Shuffle products to get variety
        random.shuffle(products)

        for idx, template in enumerate(group_templates):
            if idx >= len(products):
                break  # Don't create more groups than we have products

            product = products[idx]
            location = london_locations[idx % len(london_locations)]

            # Calculate quantities
            target_quantity = template['target']
            min_quantity = int(target_quantity * 0.6)  # 60% of target
            current_quantity = int(
                target_quantity * template['progress_level'])

            # Expiry date in future
            expires_at = timezone.now() + \
                timedelta(days=template['days_until_expiry'])

            # Determine status
            if 'status' in template:
                status = template['status']
            else:
                status = 'open'

            # Create buying group
            group = BuyingGroup.objects.create(
                product=product,
                center_point=location['point'],
                radius_km=location['radius'],
                area_name=location['name'],
                target_quantity=target_quantity,
                current_quantity=0,  # Will update after creating commitments
                min_quantity=min_quantity,
                discount_percent=Decimal(str(template['discount'])),
                expires_at=expires_at,
                status=status,
            )

            created_groups += 1

            # Create commitments to reach current_quantity
            commitments_needed = current_quantity
            quantity_allocated = 0

            # Get buyers with addresses near this location
            nearby_buyers = self._get_nearby_buyers(
                buyers,
                location['point'],
                location['radius']
            )

            if not nearby_buyers:
                # Fallback: use any buyers
                nearby_buyers = buyers

            # Shuffle to randomize commitment pattern
            random.shuffle(nearby_buyers)

            # Create 3-8 commitments per group
            num_commitments = min(random.randint(3, 8), len(nearby_buyers))

            for i in range(num_commitments):
                if quantity_allocated >= commitments_needed:
                    break

                buyer = nearby_buyers[i % len(nearby_buyers)]

                # Get buyer's address (prefer default address)
                buyer_address = buyer.addresses.filter(is_default=True).first()
                if not buyer_address:
                    buyer_address = buyer.addresses.first()

                if not buyer_address:
                    continue

                # Calculate commitment quantity
                remaining_quantity = commitments_needed - quantity_allocated

                if i == num_commitments - 1:
                    # Last commitment: allocate all remaining quantity
                    commit_quantity = remaining_quantity
                else:
                    # Random quantity between 1-20 units (or whatever is remaining)
                    max_commit = min(20, remaining_quantity)
                    # Ensure min doesn't exceed max
                    min_commit = min(5, max_commit)

                    # If we have very little left, just use what's available
                    if max_commit < 1:
                        continue  # Skip if no quantity left

                    commit_quantity = random.randint(min_commit, max_commit)

                    # Ensure we don't exceed remaining quantity
                    commit_quantity = min(commit_quantity, remaining_quantity)

                # Create commitment
                # 70% have payment intents (realistic), 30% don't (test edge cases)
                has_payment_intent = random.random() > 0.3

                GroupCommitment.objects.create(
                    group=group,
                    buyer=buyer,
                    quantity=commit_quantity,
                    buyer_location=buyer_address.location,
                    buyer_postcode=buyer_address.postcode,
                    status='pending',
                    # Add realistic test payment intent ID
                    # Format: pi_test_seed_{group_id}_{buyer_id}_{timestamp}
                    stripe_payment_intent_id=(
                        f'pi_test_seed_{group.id}_{buyer.id}_{int(timezone.now().timestamp())}'
                        if has_payment_intent
                        else None  # Some commitments have no payment intent to test edge cases
                    )
                )

                quantity_allocated += commit_quantity
                created_commitments += 1

            # Update group's current_quantity
            group.current_quantity = quantity_allocated
            group.save(update_fields=['current_quantity'])

            # Output
            progress_pct = (quantity_allocated / target_quantity *
                            100) if target_quantity > 0 else 0
            status_icon = '🎯' if status == 'active' else '⏳'
            days_left = template['days_until_expiry']

            self.stdout.write(
                f"  {status_icon} {location['name']} | {product.name[:30]:30} | "
                f"{quantity_allocated:3}/{target_quantity:3} ({progress_pct:.0f}%) | "
                f"{template['discount']}% off | {days_left}d left"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Created {created_groups} buying groups with {created_commitments} commitments'
            )
        )

        # Summary statistics
        total_groups = BuyingGroup.objects.count()
        open_groups = BuyingGroup.objects.filter(status='open').count()
        active_groups = BuyingGroup.objects.filter(status='active').count()
        total_commitments = GroupCommitment.objects.count()

        # Progress distribution
        near_complete = BuyingGroup.objects.filter(
            status='open',
            current_quantity__gte=F('target_quantity') * 0.8
        ).count()

        moderate = BuyingGroup.objects.filter(
            status='open',
            current_quantity__gte=F('target_quantity') * 0.5,
            current_quantity__lt=F('target_quantity') * 0.8
        ).count()

        just_started = BuyingGroup.objects.filter(
            status='open',
            current_quantity__lt=F('target_quantity') * 0.5
        ).count()

        self.stdout.write('\nBuying Group Statistics:')
        self.stdout.write(f'  Total groups: {total_groups}')
        self.stdout.write(f'  Open groups: {open_groups}')
        self.stdout.write(f'  Active groups: {active_groups}')
        self.stdout.write(f'  Total commitments: {total_commitments}')
        self.stdout.write(f'\nProgress Distribution:')
        self.stdout.write(f'  Near complete (80-100%): {near_complete}')
        self.stdout.write(f'  Moderate (50-80%): {moderate}')
        self.stdout.write(f'  Just started (<50%): {just_started}')

    def _get_nearby_buyers(self, buyers, center_point, radius_km):
        """
        Get buyers with addresses within radius of the group center.
        Uses simplified distance check.
        """
        nearby = []

        for buyer in buyers:
            for address in buyer.addresses.all():
                if address.location:
                    # Simple distance check using haversine
                    distance_km = self._calculate_distance(
                        center_point.y, center_point.x,
                        address.location.y, address.location.x
                    )

                    if distance_km <= radius_km:
                        nearby.append(buyer)
                        break  # Only add buyer once

        return nearby

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate distance between two points using Haversine formula.
        Returns distance in kilometers.
        """
        from math import radians, cos, sin, sqrt, atan2

        R = 6371  # Earth's radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c
