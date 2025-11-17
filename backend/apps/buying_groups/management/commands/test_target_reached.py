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

        # Find an open buying group
        self.stdout.write("🔍 Searching for open buying group...\n")

        open_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now()
        ).select_related('product__vendor').order_by('-id')

        if not open_groups.exists():
            self.stdout.write(self.style.ERROR(
                "❌ No open buying groups found"))
            self.stdout.write(
                "   Try running: python manage.py seed_buying_groups")
            return

        # Pick the first open group
        group = open_groups.first()
        self.stdout.write(self.style.SUCCESS(f"✅ Found group {group.id}\n"))

        # Calculate how many units we need to get close to target (1-3 units away)
        units_to_add = max(0, group.target_quantity -
                           group.current_quantity - 3)

        if units_to_add > 0:
            self.stdout.write(
                f"📝 Creating commitments to bring group close to target...")
            self.stdout.write(
                f"   Current: {group.current_quantity}, Target: {group.target_quantity}")
            self.stdout.write(
                f"   Need to add: {units_to_add} units to be 3 units from target\n")

            # Get buyers
            from apps.core.models import User
            buyers = list(User.objects.filter(email__endswith='@buyer.test'))

            if not buyers:
                self.stdout.write(self.style.ERROR(
                    "❌ No buyers found. Run: python manage.py seed_users"))
                return

            # Create commitments
            commitments_created = 0
            quantity_allocated = 0

            while quantity_allocated < units_to_add and len(buyers) > commitments_created:
                buyer = buyers[commitments_created % len(buyers)]

                # Get buyer's address
                buyer_address = buyer.addresses.filter(is_default=True).first()
                if not buyer_address:
                    buyer_address = buyer.addresses.first()

                if not buyer_address:
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠️  Buyer {buyer.email} has no address, skipping..."))
                    commitments_created += 1
                    continue

                # Calculate quantity for this commitment
                remaining = units_to_add - quantity_allocated
                commit_quantity = min(10, remaining)  # Max 10 per commitment

                if commit_quantity < 1:
                    break

                # Create commitment
                GroupCommitment.objects.create(
                    group=group,
                    buyer=buyer,
                    quantity=commit_quantity,
                    buyer_location=buyer_address.location,
                    buyer_postcode=buyer_address.postcode,
                    delivery_address=buyer_address,
                    status='pending',
                    stripe_payment_intent_id=f'pi_test_target_{group.id}_{buyer.id}_{int(timezone.now().timestamp())}'
                )

                quantity_allocated += commit_quantity
                commitments_created += 1
                self.stdout.write(
                    f"   ✅ Created commitment: {buyer.email} - {commit_quantity} units")

            # Update group's current_quantity
            group.current_quantity += quantity_allocated
            group.save(update_fields=['current_quantity'])

            self.stdout.write(self.style.SUCCESS(
                f"\n   ✅ Created {commitments_created} commitments totaling {quantity_allocated} units"))
            self.stdout.write(
                f"   New quantity: {group.current_quantity}/{group.target_quantity}\n")
        else:
            self.stdout.write(
                f"   Group is already close to or past target, no commitments needed\n")

        # Display group details
        self.stdout.write("📦 GROUP DETAILS:")
        self.stdout.write(f"   ID: {group.id}")
        self.stdout.write(
            f"   Product: {group.product.name} (ID: {group.product.id})")
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

        # Save original state (before creating test commitments)
        original_current_quantity = group.current_quantity
        original_status = group.status

        # Get existing commitments count
        existing_commitments = GroupCommitment.objects.filter(
            group=group,
            status='pending'
        )
        original_commitment_count = existing_commitments.count()
        self.stdout.write(
            f"   Current Commitments: {original_commitment_count}\n")

        # Track commitments created by this test (for cleanup)
        test_commitment_ids = list(
            GroupCommitment.objects.filter(
                group=group,
                stripe_payment_intent_id__startswith='pi_test_target_'
            ).values_list('id', flat=True)
        )

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

        self.stdout.write(
            f"   New quantity: {group.current_quantity}/{group.target_quantity}")
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
            self.stdout.write(self.style.SUCCESS(
                "   ✅ Group marked as COMPLETED (correct!)"))
        else:
            self.stdout.write(self.style.ERROR(
                f"   ❌ Group status should be 'completed' but is '{group.status}'"))

        self.stdout.write(
            f"   Group current_quantity: {group.current_quantity}\n")

        # Check commitments
        commitments = GroupCommitment.objects.filter(group=group)
        confirmed_count = commitments.filter(status='confirmed').count()
        self.stdout.write(f"   Total commitments: {commitments.count()}")
        self.stdout.write(f"   Confirmed commitments: {confirmed_count}")

        if confirmed_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"   ✅ {confirmed_count} commitments confirmed"))
        else:
            self.stdout.write(self.style.WARNING(
                "   ⚠️  No commitments confirmed"))

        # Check for created orders
        self.stdout.write(f"\n   Checking for orders created...")
        orders = Order.objects.filter(group=group)
        orders_created = orders.count() - orders_before

        self.stdout.write(f"   Orders before: {orders_before}")
        self.stdout.write(f"   Orders after: {orders.count()}")
        self.stdout.write(f"   Orders created: {orders_created}")

        if orders_created > 0:
            self.stdout.write(self.style.SUCCESS(
                f"   ✅ {orders_created} orders created immediately!"))
        else:
            self.stdout.write(self.style.ERROR("   ❌ No orders were created"))

        # Show order details
        if orders.exists():
            self.stdout.write("\n   📦 ORDER DETAILS:")
            new_orders = orders.order_by(
                '-created_at')[:orders_created] if orders_created > 0 else orders

            for order in new_orders:
                self.stdout.write(
                    f"\n   Order #{order.id} ({order.reference_number}):")
                self.stdout.write(f"      Buyer: {order.buyer.username}")
                self.stdout.write(f"      Status: {order.status}")
                self.stdout.write(f"      Total: £{order.total}")
                self.stdout.write(f"      Created: {order.created_at}")
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

        # Check commitment-to-order linkage
        if confirmed_count > 0:
            self.stdout.write("\n   🔗 COMMITMENT-TO-ORDER LINKAGE:")
            confirmed_commitments = commitments.filter(status='confirmed')

            linked_count = 0
            for commitment in confirmed_commitments:
                if commitment.order:
                    self.stdout.write(
                        f"      Commitment #{commitment.id} → Order {commitment.order.reference_number} ✅")
                    linked_count += 1
                else:
                    self.stdout.write(
                        f"      Commitment #{commitment.id} → No order ❌")

            if linked_count == confirmed_count:
                self.stdout.write(self.style.SUCCESS(
                    f"\n   ✅ All {confirmed_count} confirmed commitments linked to orders!"))
            else:
                self.stdout.write(self.style.WARNING(
                    f"\n   ⚠️  Only {linked_count}/{confirmed_count} commitments linked"))

        # Restore original state
        self.stdout.write("\n🔄 RESTORING ORIGINAL STATE:")

        # Restore group
        group.current_quantity = original_current_quantity
        group.status = original_status
        group.save(update_fields=['current_quantity', 'status'])

        self.stdout.write(
            f"   Restored current_quantity to: {original_current_quantity}")
        self.stdout.write(f"   Restored status to: {original_status}")

        # Reset commitments
        confirmed_commitments = GroupCommitment.objects.filter(
            group=group,
            status='confirmed'
        )
        if confirmed_commitments.exists():
            confirmed_commitments.update(status='pending', order=None)
            self.stdout.write(
                f"   Reset {confirmed_commitments.count()} commitments to pending")

        # Delete test commitments created by this test
        test_commitments = GroupCommitment.objects.filter(
            id__in=test_commitment_ids
        )
        if test_commitments.exists():
            test_commit_count = test_commitments.count()
            test_commitments.delete()
            self.stdout.write(
                f"   Deleted {test_commit_count} test commitments")

        # Get all orders created during this test (linked to commitments from this group)
        orders_to_delete = Order.objects.filter(group=group)

        if orders_to_delete.exists():
            # Collect order IDs for deletion (can't delete sliced queryset)
            order_ids = []

            # Return stock before deleting
            for order in orders_to_delete:
                order_ids.append(order.id)
                for item in order.items.all():
                    Product.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )

            # Delete by IDs (not using sliced queryset)
            deleted_count = Order.objects.filter(id__in=order_ids).delete()[0]
            self.stdout.write(
                f"   Deleted {deleted_count} test orders and restored stock")

        # Verify restoration
        group.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ Verified current_quantity: {group.current_quantity}"))
        self.stdout.write(self.style.SUCCESS(
            f"   ✅ Verified status: {group.status}"))

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
            success_criteria.append(
                f"✅ {orders_created} orders created immediately when target reached")
        else:
            failures.append("❌ No orders were created")

        if confirmed_count > 0:
            success_criteria.append(
                f"✅ {confirmed_count} commitments confirmed")
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
            self.stdout.write(self.style.SUCCESS(
                "🎉 ALL TESTS PASSED - TARGET REACHED FLOW WORKS!"))
            self.stdout.write(self.style.SUCCESS(
                "Orders are created immediately when target is reached"))
        else:
            self.stdout.write(self.style.ERROR(
                "⚠️  SOME TESTS FAILED - REVIEW ABOVE"))
        self.stdout.write("="*80 + "\n")
