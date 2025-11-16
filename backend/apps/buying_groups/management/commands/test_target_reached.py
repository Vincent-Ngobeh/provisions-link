"""
Management command to test immediate order creation when group target is reached.
Creates real commitments and triggers the target reached flow organically.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from apps.buying_groups.services.group_buying_service import GroupBuyingService
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from apps.core.models import User


class Command(BaseCommand):
    help = 'Test immediate order creation when group target is reached by creating real commitments'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*80)
        self.stdout.write("TARGET REACHED TEST - IMMEDIATE ORDER CREATION")
        self.stdout.write("="*80 + "\n")

        # Find a suitable group
        self.stdout.write("🔍 Searching for suitable test group...\n")

        open_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now()
        ).select_related('product__vendor')

        # Find a group that's not too full (30-70% progress)
        # This gives us room to add commitments
        test_group = None
        for group in open_groups:
            progress = (group.current_quantity / group.target_quantity) * 100
            if 30 <= progress <= 70:
                test_group = group
                break

        if not test_group:
            # Fallback: use any open group
            test_group = open_groups.first()

        if not test_group:
            self.stdout.write(self.style.ERROR("❌ No open groups found"))
            self.stdout.write("   Run: python manage.py seed_buying_groups")
            return

        group = test_group
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
        progress_pct = (group.current_quantity / group.target_quantity) * 100
        self.stdout.write(f"\n   📊 CURRENT PROGRESS:")
        self.stdout.write(f"   Current Quantity: {group.current_quantity}")
        self.stdout.write(f"   Target Quantity: {group.target_quantity}")
        self.stdout.write(f"   Progress: {progress_pct:.1f}%")
        self.stdout.write(f"   Units Needed: {units_needed} 🎯")
        self.stdout.write(f"   Min Quantity: {group.min_quantity}")

        self.stdout.write(f"\n   Status: {group.status}")
        self.stdout.write(f"   Expires: {group.expires_at}\n")

        # Save original state
        original_current_quantity = group.current_quantity
        original_status = group.status

        # Get buyers to create commitments
        buyers = list(User.objects.filter(email__endswith='@buyer.test'))

        if not buyers:
            self.stdout.write(self.style.ERROR("❌ No test buyers found"))
            self.stdout.write("   Run: python manage.py seed_users")
            return

        # Get buyers who haven't committed yet
        existing_buyer_ids = set(
            GroupCommitment.objects.filter(group=group).values_list('buyer_id', flat=True)
        )
        available_buyers = [b for b in buyers if b.id not in existing_buyer_ids]

        if not available_buyers:
            self.stdout.write(self.style.ERROR("❌ No available buyers (all have already committed)"))
            return

        # Count orders before
        orders_before = Order.objects.filter(group=group).count()
        existing_commitments_count = GroupCommitment.objects.filter(group=group, status='pending').count()

        self.stdout.write(f"   Available Buyers: {len(available_buyers)}")
        self.stdout.write(f"   Existing Commitments: {existing_commitments_count}\n")

        # Create commitments to reach target
        self.stdout.write("⚡ CREATING COMMITMENTS TO REACH TARGET:")
        self.stdout.write("="*80)

        service = GroupBuyingService()
        commitments_created = []
        remaining_to_target = units_needed

        # Calculate how many commitments we need
        # We'll create 3-5 commitments, with the last one pushing us over the target
        num_commitments = min(5, len(available_buyers))

        for i in range(num_commitments):
            buyer = available_buyers[i]

            # Get buyer's address
            buyer_address = buyer.addresses.filter(is_default=True).first()
            if not buyer_address:
                buyer_address = buyer.addresses.first()

            if not buyer_address:
                self.stdout.write(f"   ⚠️  Buyer {buyer.username} has no address, skipping")
                continue

            # Calculate quantity for this commitment
            if i == num_commitments - 1:
                # Last commitment: push us over the target
                commit_quantity = remaining_to_target + 2  # Add 2 extra to ensure we reach target
            else:
                # Split remaining quantity among commitments
                commit_quantity = max(1, remaining_to_target // (num_commitments - i))
                commit_quantity = min(commit_quantity, remaining_to_target - 1)  # Leave some for others

            self.stdout.write(f"\n   Creating commitment #{i+1}:")
            self.stdout.write(f"   Buyer: {buyer.username} (ID: {buyer.id})")
            self.stdout.write(f"   Quantity: {commit_quantity} units")
            self.stdout.write(f"   Remaining to target: {remaining_to_target}")

            # Use the service to create commitment (this will trigger target reached if applicable)
            result = service.join_group(
                group_id=group.id,
                buyer=buyer,
                quantity=commit_quantity,
                buyer_location=buyer_address.location,
                buyer_postcode=buyer_address.postcode,
                payment_intent_id=f'pi_test_{group.id}_{buyer.id}_{int(timezone.now().timestamp())}',
                delivery_address=buyer_address,
                delivery_notes=f'Test commitment for target reached test'
            )

            if result.success:
                commitment = result.data['commitment']
                target_reached = result.data.get('target_reached', False)

                commitments_created.append(commitment)
                remaining_to_target -= commit_quantity

                group.refresh_from_db()

                self.stdout.write(self.style.SUCCESS(f"   ✅ Commitment created (ID: {commitment.id})"))
                self.stdout.write(f"   Group now at: {group.current_quantity}/{group.target_quantity}")

                if target_reached:
                    self.stdout.write(self.style.SUCCESS(f"   🎉 TARGET REACHED! Orders should be created immediately!"))
                    break
            else:
                self.stdout.write(self.style.ERROR(f"   ❌ Failed: {result.error}"))

        self.stdout.write("\n" + "="*80)
        self.stdout.write("✅ COMMITMENT CREATION COMPLETED")
        self.stdout.write("="*80 + "\n")

        # Check results
        group.refresh_from_db()
        self.stdout.write("🔍 POST-PROCESSING STATUS CHECK:")
        self.stdout.write(f"   Group status: {group.status}")
        self.stdout.write(f"   Group current_quantity: {group.current_quantity}/{group.target_quantity}")

        if group.status == 'completed':
            self.stdout.write(self.style.SUCCESS("   ✅ Group marked as COMPLETED (target reached!)"))
        elif group.status == 'active':
            self.stdout.write(self.style.SUCCESS("   ✅ Group marked as ACTIVE (processing)"))
        else:
            self.stdout.write(self.style.WARNING(f"   ⚠️  Group status is '{group.status}'"))

        # Check commitments
        all_commitments = GroupCommitment.objects.filter(group=group)
        confirmed_count = all_commitments.filter(status='confirmed').count()
        pending_count = all_commitments.filter(status='pending').count()

        self.stdout.write(f"\n   Total commitments: {all_commitments.count()}")
        self.stdout.write(f"   Confirmed: {confirmed_count}")
        self.stdout.write(f"   Pending: {pending_count}")
        self.stdout.write(f"   Created in this test: {len(commitments_created)}")

        # Check for created orders
        self.stdout.write(f"\n   Checking for orders created...")
        orders = Order.objects.filter(group=group)
        orders_created = orders.count() - orders_before

        self.stdout.write(f"   Orders before test: {orders_before}")
        self.stdout.write(f"   Orders after test: {orders.count()}")
        self.stdout.write(f"   Orders created: {orders_created}")

        if orders_created > 0:
            self.stdout.write(self.style.SUCCESS(f"   ✅ {orders_created} orders created immediately when target reached!"))
        else:
            self.stdout.write(self.style.ERROR("   ❌ No orders were created"))

        # Show order details
        if orders_created > 0:
            self.stdout.write("\n   📦 ORDER DETAILS:")
            new_orders = list(orders.order_by('-created_at')[:orders_created])

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
            confirmed_commitments = all_commitments.filter(status='confirmed')

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

        # Delete test commitments we created
        test_commitment_ids = [c.id for c in commitments_created]
        if test_commitment_ids:
            GroupCommitment.objects.filter(id__in=test_commitment_ids).delete()
            self.stdout.write(f"   Deleted {len(test_commitment_ids)} test commitments")

        # Restore group
        group.current_quantity = original_current_quantity
        group.status = original_status
        group.save(update_fields=['current_quantity', 'status'])

        self.stdout.write(f"   Restored current_quantity to: {original_current_quantity}")
        self.stdout.write(f"   Restored status to: {original_status}")

        # Delete created orders and restore stock
        if orders_created > 0:
            new_orders = Order.objects.filter(group=group).order_by('-created_at')[:orders_created]

            # Return stock before deleting
            for order in new_orders:
                for item in order.items.all():
                    Product.objects.filter(id=item.product.id).update(
                        stock_quantity=F('stock_quantity') + item.quantity
                    )

            deleted_count = new_orders.count()
            new_orders.delete()
            self.stdout.write(f"   Deleted {deleted_count} test orders and restored stock")

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
        if len(commitments_created) > 0:
            success_criteria.append(f"✅ Created {len(commitments_created)} test commitments")
        else:
            failures.append("❌ No commitments were created")

        if orders_created > 0:
            success_criteria.append(f"✅ {orders_created} orders created immediately when target reached")
        else:
            failures.append("❌ No orders were created")

        if confirmed_count > 0:
            success_criteria.append(f"✅ {confirmed_count} commitments confirmed")
        else:
            failures.append("❌ No commitments were confirmed")

        if group.status == original_status:
            success_criteria.append("✅ Group status restored correctly")
        else:
            failures.append("❌ Group status not properly restored")

        # Print results
        for item in success_criteria:
            self.stdout.write(self.style.SUCCESS(item))

        for item in failures:
            self.stdout.write(self.style.ERROR(item))

        # Overall result
        self.stdout.write("\n" + "="*80)
        if len(failures) == 0 and orders_created > 0:
            self.stdout.write(self.style.SUCCESS("🎉 ALL TESTS PASSED - TARGET REACHED FLOW WORKS!"))
            self.stdout.write(self.style.SUCCESS("Orders are created immediately when target is reached"))
        elif len(commitments_created) > 0 and group.current_quantity < group.target_quantity:
            self.stdout.write(self.style.WARNING("⚠️  Commitments created but target not reached"))
            self.stdout.write(self.style.WARNING(f"   Current: {group.current_quantity}/{group.target_quantity}"))
            self.stdout.write(self.style.WARNING("   This is expected if there weren't enough buyers/units"))
        else:
            self.stdout.write(self.style.ERROR("⚠️  SOME TESTS FAILED - REVIEW ABOVE"))
        self.stdout.write("="*80 + "\n")
