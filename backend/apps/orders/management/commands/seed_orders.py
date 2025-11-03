# backend/apps/orders/management/commands/seed_orders.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, F, Sum
from decimal import Decimal
from datetime import timedelta
import random

from apps.orders.models import Order, OrderItem
from apps.core.models import User
from apps.vendors.models import Vendor
from apps.products.models import Product
from apps.buying_groups.models import BuyingGroup, GroupCommitment


class Command(BaseCommand):
    help = 'Seed orders with items for portfolio demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing orders before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            Order.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared existing orders'))

        # Get data
        buyers = list(User.objects.filter(email__endswith='@buyer.test'))
        vendors = list(Vendor.objects.filter(is_approved=True))

        # Get buying groups that could generate orders (active status or high completion)
        group_buying_groups = list(
            BuyingGroup.objects.filter(status='active') |
            BuyingGroup.objects.filter(
                status='open',
                current_quantity__gte=F('target_quantity') * 0.9
            )
        )

        if not buyers:
            self.stdout.write(self.style.ERROR(
                'No buyers found. Run seed_users first.'))
            return

        if not vendors:
            self.stdout.write(self.style.ERROR(
                'No vendors found. Run seed_vendors first.'))
            return

        # Order templates with status and timing
        order_templates = [
            # Delivered orders (50%) - spread over last 30 days
            {'status': 'delivered', 'days_ago': 28,
                'paid_days_offset': 0, 'delivered_days_offset': 5},
            {'status': 'delivered', 'days_ago': 25,
                'paid_days_offset': 0, 'delivered_days_offset': 4},
            {'status': 'delivered', 'days_ago': 22,
                'paid_days_offset': 0, 'delivered_days_offset': 6},
            {'status': 'delivered', 'days_ago': 20,
                'paid_days_offset': 0, 'delivered_days_offset': 5},
            {'status': 'delivered', 'days_ago': 18,
                'paid_days_offset': 0, 'delivered_days_offset': 4},
            {'status': 'delivered', 'days_ago': 15,
                'paid_days_offset': 0, 'delivered_days_offset': 7},
            {'status': 'delivered', 'days_ago': 12,
                'paid_days_offset': 0, 'delivered_days_offset': 5},
            {'status': 'delivered', 'days_ago': 10,
                'paid_days_offset': 0, 'delivered_days_offset': 4},
            {'status': 'delivered', 'days_ago': 8,
                'paid_days_offset': 0, 'delivered_days_offset': 3},
            {'status': 'delivered', 'days_ago': 6,
                'paid_days_offset': 0, 'delivered_days_offset': 4},
            {'status': 'delivered', 'days_ago': 5,
                'paid_days_offset': 0, 'delivered_days_offset': 3},
            {'status': 'delivered', 'days_ago': 3,
                'paid_days_offset': 0, 'delivered_days_offset': 2},

            # Paid orders (20%) - awaiting fulfillment
            {'status': 'paid', 'days_ago': 2, 'paid_days_offset': 0},
            {'status': 'paid', 'days_ago': 3, 'paid_days_offset': 0},
            {'status': 'paid', 'days_ago': 4, 'paid_days_offset': 0},
            {'status': 'paid', 'days_ago': 5, 'paid_days_offset': 0},

            # Processing orders (15%) - being prepared
            {'status': 'processing', 'days_ago': 1, 'paid_days_offset': 0},
            {'status': 'processing', 'days_ago': 2, 'paid_days_offset': 0},
            {'status': 'processing', 'days_ago': 3, 'paid_days_offset': 0},

            # Shipped orders (10%) - in transit
            {'status': 'shipped', 'days_ago': 4, 'paid_days_offset': 0},
            {'status': 'shipped', 'days_ago': 6, 'paid_days_offset': 0},

            # Cancelled orders (5%) - for refund testing
            {'status': 'cancelled', 'days_ago': 7, 'paid_days_offset': 0},
        ]

        created_orders = 0
        created_items = 0
        group_orders = 0

        for idx, template in enumerate(order_templates):
            # Select random buyer and vendor
            buyer = random.choice(buyers)
            vendor = random.choice(vendors)

            # Get buyer's delivery address
            delivery_address = buyer.addresses.filter(is_default=True).first()
            if not delivery_address:
                delivery_address = buyer.addresses.first()

            if not delivery_address:
                continue  # Skip if buyer has no address

            # Get vendor's products
            vendor_products = list(Product.objects.filter(
                vendor=vendor,
                is_active=True,
                stock_quantity__gt=0
            ))

            if not vendor_products:
                continue  # Skip if vendor has no products

            # Decide if this is a group buying order (30-40% chance)
            is_group_order = (
                random.random() < 0.35 and
                group_buying_groups and
                idx < 8  # Only first 8 orders can be from groups
            )

            linked_group = None
            if is_group_order:
                # Find a group with this buyer's commitment
                buyer_commitments = GroupCommitment.objects.filter(
                    buyer=buyer,
                    status='pending',
                    order__isnull=True,  # Not yet converted to order
                    group__in=group_buying_groups
                ).select_related('group')

                if buyer_commitments.exists():
                    commitment = random.choice(list(buyer_commitments))
                    linked_group = commitment.group
                    group_orders += 1

            # Calculate timestamps
            created_at = timezone.now() - timedelta(days=template['days_ago'])
            paid_at = None
            delivered_at = None

            if template['status'] in ['paid', 'processing', 'shipped', 'delivered']:
                paid_at = created_at + timedelta(hours=random.randint(1, 6))

            if template['status'] == 'delivered':
                delivered_at = created_at + \
                    timedelta(days=template['delivered_days_offset'])

            # Create order (initial - will update totals after items)
            order = Order.objects.create(
                buyer=buyer,
                vendor=vendor,
                delivery_address=delivery_address,
                group=linked_group,
                subtotal=Decimal('0.00'),
                vat_amount=Decimal('0.00'),
                delivery_fee=Decimal(
                    str(random.choice([5.00, 7.50, 10.00, 12.00, 15.00]))),
                total=Decimal('0.00'),
                status=template['status'],
                created_at=created_at,
                paid_at=paid_at,
                delivered_at=delivered_at,
                # CHANGE 5: Use None instead of empty string for unpaid orders
                stripe_payment_intent_id=(
                    f'pi_3Demo{random.randint(100000, 999999)}'
                    if paid_at
                    else None  # Use None instead of empty string
                ),
            )

            # Create order items (2-5 items per order)
            num_items = random.randint(2, 5)
            selected_products = random.sample(
                vendor_products,
                min(num_items, len(vendor_products))
            )

            order_subtotal = Decimal('0.00')
            order_vat = Decimal('0.00')

            for product in selected_products:
                quantity = random.randint(2, 10)
                unit_price = product.price

                # Apply discount if group order
                discount_amount = Decimal('0.00')
                if linked_group and linked_group.product == product:
                    discount_percent = linked_group.discount_percent / 100
                    discount_amount = unit_price * quantity * discount_percent

                total_price = (unit_price * quantity) - discount_amount
                vat_amount = total_price * product.vat_rate

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    discount_amount=discount_amount,
                )

                order_subtotal += total_price
                order_vat += vat_amount
                created_items += 1

            # Update order totals
            order.subtotal = order_subtotal
            order.vat_amount = order_vat
            order.total = order_subtotal + order_vat + order.delivery_fee
            order.marketplace_fee = order_subtotal * vendor.commission_rate
            order.vendor_payout = order.total - order.marketplace_fee
            order.save()

            # Link commitment to order if group order
            if linked_group and is_group_order:
                commitment = GroupCommitment.objects.filter(
                    buyer=buyer,
                    group=linked_group,
                    order__isnull=True
                ).first()

                if commitment:
                    commitment.order = order
                    commitment.status = 'confirmed'
                    commitment.save()

            created_orders += 1

            # Output
            status_icon = {
                'delivered': '[DELIVERED]',
                'paid': '[PAID]',
                'processing': '[PROCESSING]',
                'shipped': '[SHIPPED]',
                'cancelled': '[CANCELLED]',
            }.get(template['status'], '[PENDING]')

            group_indicator = ' [GROUP]' if linked_group else ''
            days_ago = template['days_ago']

            self.stdout.write(
                f"  {status_icon} {order.reference_number} | "
                f"{buyer.first_name} {buyer.last_name} -> {vendor.business_name[:25]:25} | "
                f"£{order.total:6.2f} | {days_ago:2}d ago{group_indicator}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nCreated {created_orders} orders with {created_items} items '
                f'({group_orders} from buying groups)'
            )
        )

        # Summary statistics
        total_orders = Order.objects.count()
        total_items = OrderItem.objects.count()

        status_counts = {}
        for status_code, _ in Order.STATUS_CHOICES:
            count = Order.objects.filter(status=status_code).count()
            if count > 0:
                status_counts[status_code] = count

        total_revenue = Order.objects.filter(
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).aggregate(
            total=Sum('total')
        )['total'] or Decimal('0.00')

        total_commission = Order.objects.filter(
            status__in=['paid', 'processing', 'shipped', 'delivered']
        ).aggregate(
            total=Sum('marketplace_fee')
        )['total'] or Decimal('0.00')

        group_order_count = Order.objects.filter(group__isnull=False).count()

        self.stdout.write('\nOrder Statistics:')
        self.stdout.write(f'  Total orders: {total_orders}')
        self.stdout.write(f'  Total items: {total_items}')
        self.stdout.write(f'  Orders from buying groups: {group_order_count}')
        self.stdout.write(f'\nStatus Distribution:')
        for status_code, count in sorted(status_counts.items()):
            self.stdout.write(f'  {status_code}: {count}')
        self.stdout.write(f'\nFinancial Summary:')
        self.stdout.write(f'  Total revenue: £{total_revenue:,.2f}')
        self.stdout.write(f'  Platform commission: £{total_commission:,.2f}')
        self.stdout.write(
            f'  Vendor payouts: £{(total_revenue - total_commission):,.2f}')
