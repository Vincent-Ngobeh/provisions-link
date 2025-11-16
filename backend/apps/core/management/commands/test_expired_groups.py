"""
Management command to test expired groups processing with detailed logging.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.buying_groups.services.group_buying_service import GroupBuyingService
from apps.orders.models import Order, OrderItem


class Command(BaseCommand):
    help = 'Test expired groups processing with verbose output'

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            default='successful',
            choices=['successful', 'failed', 'any'],
            help='Type of group to test: successful (meets min_quantity), failed (does not meet min_quantity), or any'
        )

    def handle(self, *args, **options):
        mode = options['mode']

        self.stdout.write("\n" + "="*80)
        self.stdout.write("VERBOSE EXPIRED GROUPS TEST - DETAILED LOGGING")
        self.stdout.write("="*80 + "\n")

        # Environment check
        self.stdout.write("🔍 ENVIRONMENT CHECK:")
        self.stdout.write(f"   Current time (UTC): {timezone.now()}")
        self.stdout.write(f"   Database: default")
        self.stdout.write(
            f"   Total BuyingGroups in DB: {BuyingGroup.objects.count()}")
        self.stdout.write(f"   Total Orders in DB: {Order.objects.count()}\n")

        # Find appropriate group based on mode
        self.stdout.write(f"🔍 Searching for {mode} group...")

        open_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now()
        ).select_related('product__vendor')

        group = None

        if mode == 'successful':
            # Find a group where current_quantity >= min_quantity
            for g in open_groups:
                if g.current_quantity >= g.min_quantity:
                    group = g
                    break
        elif mode == 'failed':
            # Find a group where current_quantity < min_quantity
            for g in open_groups:
                if g.current_quantity < g.min_quantity:
                    group = g
                    break
        else:  # any
            group = open_groups.first()

        if not group:
            self.stdout.write(self.style.ERROR(f"❌ No {mode} group found"))
            return

        self.stdout.write(self.style.SUCCESS(f"✅ Found group {group.id}\n"))

        # Display group details
        self.stdout.write("📦 GROUP DETAILS:")
        self.stdout.write(f"   ID: {group.id}")
        self.stdout.write(
            f"   Product: {group.product.name} (ID: {group.product.id})")
        self.stdout.write(
            f"   Vendor: {group.product.vendor.business_name} (ID: {group.product.vendor.id})")
        self.stdout.write(f"   Product Price: £{group.product.price}")
        self.stdout.write(f"   Discount: {group.discount_percent}%")
        self.stdout.write(f"   Discounted Price: £{group.discounted_price}")
        self.stdout.write(
            f"   Progress: {group.current_quantity}/{group.target_quantity}")
        self.stdout.write(f"   Min Quantity: {group.min_quantity}")

        will_succeed = group.current_quantity >= group.min_quantity
        outcome = "✅ WILL SUCCEED" if will_succeed else "❌ WILL FAIL"
        self.stdout.write(f"   Expected Outcome: {outcome}")

        self.stdout.write(f"   Status: {group.status}")
        self.stdout.write(f"   Expires: {group.expires_at}\n")

        # Get commitments
        self.stdout.write("🔍 Fetching commitments...\n")
        commitments = GroupCommitment.objects.filter(
            group=group,
            status='pending'
        ).select_related('buyer', 'delivery_address')

        self.stdout.write(f"📋 COMMITMENTS ({commitments.count()} total):\n")

        for i, commitment in enumerate(commitments, 1):
            self.stdout.write(f"  Commitment #{i} (ID: {commitment.id}):")
            self.stdout.write(
                f"    Buyer: {commitment.buyer.username} (ID: {commitment.buyer.id})")
            self.stdout.write(f"    Email: {commitment.buyer.email}")
            self.stdout.write(f"    Quantity: {commitment.quantity}")
            self.stdout.write(f"    Status: {commitment.status}")
            self.stdout.write(
                f"    Payment Intent: {commitment.stripe_payment_intent_id or 'None'}")
            self.stdout.write(
                f"    Buyer Location: {commitment.buyer_location}")
            self.stdout.write(
                f"    Buyer Postcode: {commitment.buyer_postcode}")

            if commitment.delivery_address:
                addr = commitment.delivery_address
                self.stdout.write(
                    f"    Delivery Address Object: {addr.address_name} - {addr.postcode}")
                self.stdout.write(f"      → Address ID: {addr.id}")
                self.stdout.write(
                    f"      → User: {addr.user.username} (ID: {addr.user.id})")
                self.stdout.write(f"      → Address Name: {addr.address_name}")
                self.stdout.write(f"      → Recipient: {addr.recipient_name}")
                self.stdout.write(f"      → City: {addr.city}")
                self.stdout.write(f"      → Postcode: {addr.postcode}")
                self.stdout.write(f"      → Default: {addr.is_default}")
                self.stdout.write(f"      → Location: {addr.location}")
            else:
                self.stdout.write(f"    Delivery Address: None")
            self.stdout.write("")

        # Save original state
        original_expires_at = group.expires_at
        original_status = group.status

        # Expire the group
        self.stdout.write("⏰ EXPIRING GROUP:")
        self.stdout.write(f"   Original expiry: {original_expires_at}")
        self.stdout.write(f"   Original status: {original_status}")

        # Set expiry to past
        new_expires_at = timezone.now() - timezone.timedelta(hours=1)
        group.expires_at = new_expires_at
        group.save(update_fields=['expires_at'])

        self.stdout.write(f"   New expiry: {new_expires_at}")
        self.stdout.write(self.style.SUCCESS("   ✅ Group expired"))

        # Verify expiry
        group.refresh_from_db()
        self.stdout.write(f"   Verified expires_at: {group.expires_at}\n")

        # Process expired groups
        self.stdout.write("🔄 PROCESSING EXPIRED GROUP:")
        self.stdout.write("="*80)
        self.stdout.write(
            "📞 Calling GroupBuyingService.process_expired_groups()...")

        service = GroupBuyingService()
        self.stdout.write(f"   Service instance: {service}")
        self.stdout.write(f"   Time before call: {timezone.now()}")

        stats = service.process_expired_groups()

        self.stdout.write("\n" + "="*80)
        self.stdout.write("✅ SERVICE CALL COMPLETED")
        self.stdout.write("="*80 + "\n")

        self.stdout.write(f"📊 Stats returned: {stats}")
        self.stdout.write(f"   Type: {type(stats)}")
        self.stdout.write(
            f"   total_processed: {stats.get('total_processed', 0)}")
        self.stdout.write(f"   successful: {stats.get('successful', 0)}")
        self.stdout.write(f"   failed: {stats.get('failed', 0)}\n")

        # Check post-processing status
        group.refresh_from_db()
        self.stdout.write("🔍 POST-PROCESSING STATUS CHECK:")
        self.stdout.write(f"   Group status: {group.status}")
        self.stdout.write(
            f"   Group current_quantity: {group.current_quantity}\n")

        # Check commitments status
        commitments = GroupCommitment.objects.filter(group=group)
        self.stdout.write(f"   Total commitments: {commitments.count()}")
        for commitment in commitments:
            self.stdout.write(
                f"   - Commitment {commitment.id}: status={commitment.status}")

        # Check for created orders
        self.stdout.write(
            f"\n   Checking for orders created from this group...")
        orders = Order.objects.filter(group=group)
        self.stdout.write(
            f"   Orders created for this group: {orders.count()}")

        if orders.exists():
            self.stdout.write("\n   📦 ORDER DETAILS:")
            for order in orders:
                self.stdout.write(
                    f"\n   Order #{order.id} ({order.reference_number}):")
                self.stdout.write(f"      Buyer: {order.buyer.username}")
                self.stdout.write(f"      Status: {order.status}")
                self.stdout.write(f"      Total: £{order.total}")
                self.stdout.write(f"      Items: {order.items.count()}")

                for item in order.items.all():
                    self.stdout.write(
                        f"         - {item.quantity}x {item.product.name} @ £{item.unit_price}")
                    if item.group_commitment:
                        self.stdout.write(
                            f"           ✅ Linked to commitment #{item.group_commitment.id}")
                    else:
                        self.stdout.write(
                            f"           ⚠️  No group_commitment link!")

        # Direct order creation test for successful groups
        if will_succeed and stats.get('successful', 0) > 0:
            self.stdout.write("\n" + "="*80)
            self.stdout.write("✅ SUCCESSFUL GROUP - ORDERS SHOULD BE CREATED")
            self.stdout.write("="*80)

            confirmed_commitments = GroupCommitment.objects.filter(
                group=group,
                status='confirmed'
            )
            self.stdout.write(
                f"\n   Confirmed commitments: {confirmed_commitments.count()}")

            for commitment in confirmed_commitments:
                self.stdout.write(f"\n   Commitment #{commitment.id}:")
                self.stdout.write(f"      Buyer: {commitment.buyer.username}")
                self.stdout.write(f"      Status: {commitment.status}")
                if commitment.order:
                    self.stdout.write(
                        f"      ✅ Order created: {commitment.order.reference_number}")
                else:
                    self.stdout.write(f"      ❌ No order linked!")

        elif not will_succeed:
            self.stdout.write("\n" + "="*80)
            self.stdout.write("🧪 DIRECT ORDER CREATION TEST")
            self.stdout.write("="*80)

            test_commitment = commitments.first()
            if test_commitment:
                self.stdout.write(
                    f"📝 Testing with Commitment {test_commitment.id}:")
                self.stdout.write(f"   Status: {test_commitment.status}")
                self.stdout.write(
                    f"   Buyer: {test_commitment.buyer.username} (ID: {test_commitment.buyer.id})")
                self.stdout.write(f"   Quantity: {test_commitment.quantity}")
                self.stdout.write(
                    f"   Payment Intent: {test_commitment.stripe_payment_intent_id or 'None'}")

                if test_commitment.delivery_address:
                    addr = test_commitment.delivery_address
                    self.stdout.write(
                        f"   Delivery Address: {addr.address_name} - {addr.postcode}")
                    self.stdout.write(f"   Address Details:")
                    self.stdout.write(f"      ID: {addr.id}")
                    self.stdout.write(f"      User: {addr.user.username}")
                    self.stdout.write(
                        f"      Address Name: {addr.address_name}")
                    self.stdout.write(
                        f"      Recipient: {addr.recipient_name}")
                    self.stdout.write(
                        f"      Full: {addr.city}, {addr.postcode}\n")

                if test_commitment.status == 'cancelled':
                    self.stdout.write(
                        "ℹ️  Commitment already processed (status: cancelled)")
                    self.stdout.write("   Skipping direct order creation test")

        # Restore original state
        self.stdout.write("\n🔄 RESTORING ORIGINAL STATE:")
        group.expires_at = original_expires_at
        group.status = original_status
        group.save(update_fields=['expires_at', 'status'])

        self.stdout.write(f"   Restoring expires_at to: {original_expires_at}")
        self.stdout.write(f"   Restoring status to: {original_status}")

        # Reset commitments if they were cancelled or confirmed
        cancelled_or_confirmed = GroupCommitment.objects.filter(
            group=group,
            status__in=['cancelled', 'confirmed']
        )
        if cancelled_or_confirmed.exists():
            cancelled_or_confirmed.update(status='pending', order=None)
            self.stdout.write(
                f"   Reset {cancelled_or_confirmed.count()} commitments to pending")

        # Delete any orders that were created during the test
        orders_to_delete = Order.objects.filter(group=group)
        if orders_to_delete.exists():
            order_count = orders_to_delete.count()
            # Return stock before deleting orders
            for order in orders_to_delete:
                for item in order.items.all():
                    from django.db.models import F
                    from apps.products.models import Product
                    Product.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )
            orders_to_delete.delete()
            self.stdout.write(
                f"   Deleted {order_count} test orders and restored stock")

        # Verify restoration
        group.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ Verified group expires_at: {group.expires_at}"))
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ Verified group status: {group.status}"))

        # Summary
        self.stdout.write("\n" + "="*80)
        if will_succeed and stats.get('successful', 0) > 0:
            self.stdout.write(self.style.SUCCESS(
                "✅ VERBOSE TEST COMPLETE - GROUP SUCCEEDED"))
        elif not will_succeed and stats.get('failed', 0) > 0:
            self.stdout.write(self.style.SUCCESS(
                "✅ VERBOSE TEST COMPLETE - GROUP FAILED AS EXPECTED"))
        else:
            self.stdout.write(self.style.WARNING(
                "⚠️  VERBOSE TEST COMPLETE - UNEXPECTED RESULT"))
        self.stdout.write("="*80 + "\n")
