"""
Management command to test immediate order creation when group target is reached.
Tests the 'target reached' flow where orders are created immediately without waiting for expiry.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.buying_groups.services.group_buying_service import GroupBuyingService
from apps.orders.models import Order, OrderItem
from apps.products.models import Product


class Command(BaseCommand):
    help = 'Test immediate order creation when group target is reached'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*80)
        self.stdout.write("TARGET REACHED TEST - IMMEDIATE ORDER CREATION")
        self.stdout.write("="*80 + "\n")

        # Find a group close to target
        self.stdout.write("🔍 Searching for group close to target...\n")

        open_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now()
        ).select_related('product__vendor')

        # Find a group where we need just 1-5 more units to reach target
        target_group = None
        for group in open_groups:
            units_needed = group.target_quantity - group.current_quantity
            if 1 <= units_needed <= 5:
                target_group = group
                break

        if not target_group:
            self.stdout.write(self.style.ERROR("❌ No suitable group found (need a group 1-5 units from target)"))
            self.stdout.write("   Try running the seed command to create more groups")
            return

        group = target_group
        self.stdout.write(self.style.SUCCESS(f"✅ Found group {group.id}\n"))

        # Display group details
        self.stdout.write("📦 GROUP DETAILS:")
        self.stdout.write(f"   ID: {group.id}")
        self.stdout.write(f"   Product: {group.product.name} (ID: {group.product.id})")
        self.stdout.write(f"   Vendor: {group.product.vendor.business_name}")
        self.stdout.write(f"   Product Price: £{group.product.price}")
        self.stdout.write(f"   Discount: {group.discount_percent}%")
        self.stdout.write(f"   Discounted Price: £{group.discounted_price}")

        units_needed = group.target_quantity - group.current_quantity
        self.stdout.write(f"\n   📊 PROGRESS:")
        self.stdout.write(f"   Current Quantity: {group.current_quantity}")
        self.stdout.write(f"   Target Quantity: {group.target_quantity}")
        self.stdout.write(f"   Units Needed: {units_needed} 🎯")
        self.stdout.write(f"   Min Quantity: {group.min_quantity}")

        self.stdout.write(f"\n   Status: {group.status}")
        self.stdout.write(f"   Expires: {group.expires_at}\n")

        # Save original state
        original_current_quantity = group.current_quantity
        original_status = group.status

        # Get existing commitments count
        existing_commitments = GroupCommitment.objects.filter(
            group=group,
            status='pending'
        )
        original_commitment_count = existing_commitments.count()
        self.stdout.write(f"   Current Commitments: {original_commitment_count}\n")

        # Count orders before
        orders_before = Order.objects.filter(group=group).count()

        # Simulate reaching target by temporarily increasing current_quantity
        self.stdout.write("⚡ SIMULATING TARGET REACHED:")
        self.stdout.write(f"   Adding {units_needed} units to reach target...")

        # Temporarily update the quantity to reach target
        BuyingGroup.objects.filter(id=group.id).update(
            current_quantity=F('current_quantity') + units_needed
        )
        group.refresh_from_db()

        self.stdout.write(f"   New quantity: {group.current_quantity}/{group.target_quantity}")
        self.stdout.write(self.style.SUCCESS("   ✅ Target reached!\n"))

        # Now trigger the target reached logic
        self.stdout.write("🔄 TRIGGERING TARGET REACHED PROCESSING:")
        self.stdout.write("="*80)

        # Change status to active and call the handler
        group.status = 'active'
        group.save(update_fields=['status'])

        service = GroupBuyingService()
        self.stdout.write(f"   Service instance: {service}")
        self.stdout.write(f"   Time: {timezone.now()}")
        self.stdout.write("   Calling _handle_target_reached()...")

        # Call the target reached handler
        service._handle_target_reached(group)

        self.stdout.write("\n" + "="*80)
        self.stdout.write("✅ TARGET REACHED PROCESSING COMPLETED")
        self.stdout.write("="*80 + "\n")

        # Check results
        group.refresh_from_db()
        self.stdout.write("🔍 POST-PROCESSING STATUS CHECK:")
        self.stdout.write(f"   Group status: {group.status}")

        if group.status == 'completed':
            self.stdout.write(self.style.SUCCESS("   ✅ Group marked as COMPLETED (correct!)"))
        else:
            self.stdout.write(self.style.ERROR(f"   ❌ Group status should be 'completed' but is '{group.status}'"))

        self.stdout.write(f"   Group current_quantity: {group.current_quantity}\n")

        # Check commitments
        commitments = GroupCommitment.objects.filter(group=group)
        confirmed_count = commitments.filter(status='confirmed').count()
        self.stdout.write(f"   Total commitments: {commitments.count()}")
        self.stdout.write(f"   Confirmed commitments: {confirmed_count}")

        if confirmed_count > 0:
            self.stdout.write(self.style.SUCCESS(f"   ✅ {confirmed_count} commitments confirmed"))
        else:
            self.stdout.write(self.style.WARNING("   ⚠️  No commitments confirmed"))

        # Check for created orders
        self.stdout.write(f"\n   Checking for orders created...")
        orders = Order.objects.filter(group=group)
        orders_created = orders.count() - orders_before

        self.stdout.write(f"   Orders before: {orders_before}")
        self.stdout.write(f"   Orders after: {orders.count()}")
        self.stdout.write(f"   Orders created: {orders_created}")

        if orders_created > 0:
            self.stdout.write(self.style.SUCCESS(f"   ✅ {orders_created} orders created immediately!"))
        else:
            self.stdout.write(self.style.ERROR("   ❌ No orders were created"))

        # Show order details
        if orders.exists():
            self.stdout.write("\n   📦 ORDER DETAILS:")
            new_orders = orders.order_by('-created_at')[:orders_created] if orders_created > 0 else orders

            for order in new_orders:
                self.stdout.write(f"\n   Order #{order.id} ({order.reference_number}):")
                self.stdout.write(f"      Buyer: {order.buyer.username}")
                self.stdout.write(f"      Status: {order.status}")
                self.stdout.write(f"      Total: £{order.total}")
                self.stdout.write(f"      Created: {order.created_at}")
                self.stdout.write(f"      Items: {order.items.count()}")

                for item in order.items.all():
                    self.stdout.write(f"         - {item.quantity}x {item.product.name} @ £{item.unit_price}")
                    if item.group_commitment:
                        self.stdout.write(f"           ✅ Linked to commitment #{item.group_commitment.id}")
                    else:
                        self.stdout.write(f"           ⚠️  No group_commitment link!")

        # Check commitment-to-order linkage
        if confirmed_count > 0:
            self.stdout.write("\n   🔗 COMMITMENT-TO-ORDER LINKAGE:")
            confirmed_commitments = commitments.filter(status='confirmed')

            linked_count = 0
            for commitment in confirmed_commitments:
                if commitment.order:
                    self.stdout.write(f"      Commitment #{commitment.id} → Order {commitment.order.reference_number} ✅")
                    linked_count += 1
                else:
                    self.stdout.write(f"      Commitment #{commitment.id} → No order ❌")

            if linked_count == confirmed_count:
                self.stdout.write(self.style.SUCCESS(f"\n   ✅ All {confirmed_count} confirmed commitments linked to orders!"))
            else:
                self.stdout.write(self.style.WARNING(f"\n   ⚠️  Only {linked_count}/{confirmed_count} commitments linked"))

        # Restore original state
        self.stdout.write("\n🔄 RESTORING ORIGINAL STATE:")

        # Restore group
        group.current_quantity = original_current_quantity
        group.status = original_status
        group.save(update_fields=['current_quantity', 'status'])

        self.stdout.write(f"   Restored current_quantity to: {original_current_quantity}")
        self.stdout.write(f"   Restored status to: {original_status}")

        # Reset commitments
        confirmed_commitments = GroupCommitment.objects.filter(
            group=group,
            status='confirmed'
        )
        if confirmed_commitments.exists():
            confirmed_commitments.update(status='pending', order=None)
            self.stdout.write(f"   Reset {confirmed_commitments.count()} commitments to pending")

        # Delete created orders and restore stock
        new_orders = Order.objects.filter(group=group).order_by('-created_at')[:orders_created] if orders_created > 0 else Order.objects.none()
        if new_orders.exists():
            order_count = new_orders.count()

            # Return stock before deleting
            for order in new_orders:
                for item in order.items.all():
                    Product.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )

            new_orders.delete()
            self.stdout.write(f"   Deleted {order_count} test orders and restored stock")

        # Verify restoration
        group.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(f"   ✅ Verified current_quantity: {group.current_quantity}"))
        self.stdout.write(self.style.SUCCESS(f"   ✅ Verified status: {group.status}"))

        # Summary
        self.stdout.write("\n" + "="*80)
        self.stdout.write("📊 TEST SUMMARY:")
        self.stdout.write("="*80)

        success_criteria = []
        failures = []

        # Check each criterion
        if group.status == original_status:
            success_criteria.append("✅ Group status restored correctly")
        else:
            failures.append("❌ Group status not restored")

        if orders_created > 0:
            success_criteria.append(f"✅ {orders_created} orders created immediately when target reached")
        else:
            failures.append("❌ No orders were created")

        if confirmed_count > 0:
            success_criteria.append(f"✅ {confirmed_count} commitments confirmed")
        else:
            failures.append("❌ No commitments were confirmed")

        # Print results
        for item in success_criteria:
            self.stdout.write(self.style.SUCCESS(item))

        for item in failures:
            self.stdout.write(self.style.ERROR(item))

        # Overall result
        self.stdout.write("\n" + "="*80)
        if len(failures) == 0:
            self.stdout.write(self.style.SUCCESS("🎉 ALL TESTS PASSED - TARGET REACHED FLOW WORKS!"))
            self.stdout.write(self.style.SUCCESS("Orders are created immediately when target is reached"))
        else:
            self.stdout.write(self.style.ERROR("⚠️  SOME TESTS FAILED - REVIEW ABOVE"))
        self.stdout.write("="*80 + "\n")
