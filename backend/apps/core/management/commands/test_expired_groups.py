# backend/apps/core/management/commands/test_expired_groups_verbose.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import traceback
import sys


class Command(BaseCommand):
    help = 'Test expired groups with EXTENSIVE logging to debug order creation failures'

    def add_arguments(self, parser):
        parser.add_argument(
            '--group-id',
            type=int,
            default=None,
            help='Specific group ID to test (optional)',
        )

    def handle(self, *args, **options):
        from apps.buying_groups.models import BuyingGroup, GroupCommitment
        from apps.orders.services.order_service import OrderService
        from apps.orders.models import Order

        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.WARNING(
            'VERBOSE EXPIRED GROUPS TEST - DETAILED LOGGING'))
        self.stdout.write('='*80 + '\n')

        group_id = options.get('group_id')

        # Environment check
        self.stdout.write('\n🔍 ENVIRONMENT CHECK:')
        self.stdout.write(f'   Current time (UTC): {timezone.now()}')
        self.stdout.write(f'   Database: {Order.objects.db}')
        self.stdout.write(
            f'   Total BuyingGroups in DB: {BuyingGroup.objects.count()}')
        self.stdout.write(f'   Total Orders in DB: {Order.objects.count()}')

        # Find a group to test
        if group_id:
            try:
                group = BuyingGroup.objects.get(id=group_id)
                self.stdout.write(f'\n✅ Testing specific group {group_id}')
            except BuyingGroup.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f'❌ Group {group_id} not found'))
                return
        else:
            # Find first open group
            self.stdout.write('\n🔍 Searching for open group...')
            group = BuyingGroup.objects.filter(
                status='open',
                expires_at__gt=timezone.now()
            ).first()

            if not group:
                self.stdout.write(self.style.ERROR(
                    '❌ No open groups found. Run: python manage.py seed_buying_groups'))
                return
            self.stdout.write(f'✅ Found group {group.id}')

        self.stdout.write(f'\n📦 GROUP DETAILS:')
        self.stdout.write(f'   ID: {group.id}')
        self.stdout.write(
            f'   Product: {group.product.name} (ID: {group.product.id})')
        self.stdout.write(
            f'   Vendor: {group.product.vendor.business_name} (ID: {group.product.vendor.id})')
        self.stdout.write(f'   Product Price: £{group.product.price}')
        self.stdout.write(f'   Discount: {group.discount_percent}%')
        self.stdout.write(f'   Discounted Price: £{group.discounted_price}')
        self.stdout.write(
            f'   Progress: {group.current_quantity}/{group.target_quantity}')
        self.stdout.write(f'   Min Quantity: {group.min_quantity}')
        self.stdout.write(f'   Status: {group.status}')
        self.stdout.write(f'   Expires: {group.expires_at}')

        # Get commitments
        self.stdout.write('\n🔍 Fetching commitments...')
        commitments = GroupCommitment.objects.filter(
            group=group,
            status='pending'
        ).select_related('buyer', 'delivery_address')

        self.stdout.write(f'\n📋 COMMITMENTS ({commitments.count()} total):')
        for i, commitment in enumerate(commitments, 1):
            self.stdout.write(f'\n  Commitment #{i} (ID: {commitment.id}):')
            self.stdout.write(
                f'    Buyer: {commitment.buyer.username} (ID: {commitment.buyer.id})')
            self.stdout.write(f'    Email: {commitment.buyer.email}')
            self.stdout.write(f'    Quantity: {commitment.quantity}')
            self.stdout.write(f'    Status: {commitment.status}')
            self.stdout.write(
                f'    Payment Intent: {commitment.stripe_payment_intent_id}')
            self.stdout.write(
                f'    Buyer Location: {commitment.buyer_location}')
            self.stdout.write(
                f'    Buyer Postcode: {commitment.buyer_postcode}')

            # Delivery address details
            self.stdout.write(
                f'    Delivery Address Object: {commitment.delivery_address}')
            if commitment.delivery_address:
                addr = commitment.delivery_address
                self.stdout.write(f'      → Address ID: {addr.id}')
                self.stdout.write(
                    f'      → User: {addr.user.username} (ID: {addr.user.id})')
                self.stdout.write(f'      → Name: {addr.address_name}')
                self.stdout.write(f'      → City: {addr.city}')
                self.stdout.write(f'      → Postcode: {addr.postcode}')
                self.stdout.write(f'      → Default: {addr.is_default}')
                self.stdout.write(f'      → Location: {addr.location}')
            else:
                self.stdout.write(self.style.ERROR(
                    '      → ❌ NO DELIVERY ADDRESS!'))

        # Force group to expire
        self.stdout.write(f'\n⏰ EXPIRING GROUP:')
        original_expiry = group.expires_at
        original_status = group.status
        self.stdout.write(f'   Original expiry: {original_expiry}')
        self.stdout.write(f'   Original status: {original_status}')

        new_expiry = timezone.now() - timedelta(hours=1)
        self.stdout.write(f'   New expiry: {new_expiry}')

        group.expires_at = new_expiry
        group.save(update_fields=['expires_at'])
        self.stdout.write('   ✅ Group expired')

        # Verify the update
        group.refresh_from_db()
        self.stdout.write(f'   Verified expires_at: {group.expires_at}')

        # Manually process the group (simulating what the Celery task does)
        self.stdout.write('\n🔄 PROCESSING EXPIRED GROUP:')
        self.stdout.write('='*80)

        from apps.buying_groups.services.group_buying_service import GroupBuyingService
        service = GroupBuyingService()

        try:
            self.stdout.write(
                '📞 Calling GroupBuyingService.process_expired_groups()...')
            self.stdout.write(f'   Service instance: {service}')
            self.stdout.write(f'   Time before call: {timezone.now()}\n')

            stats = service.process_expired_groups()

            self.stdout.write('\n' + '='*80)
            self.stdout.write(self.style.SUCCESS('✅ SERVICE CALL COMPLETED'))
            self.stdout.write('='*80)
            self.stdout.write(f'\n📊 Stats returned: {stats}')
            self.stdout.write(f'   Type: {type(stats)}')
            if isinstance(stats, dict):
                for key, value in stats.items():
                    self.stdout.write(f'   {key}: {value}')

        except Exception as e:
            self.stdout.write('\n' + '='*80)
            self.stdout.write(self.style.ERROR(
                '❌ EXCEPTION DURING PROCESSING'))
            self.stdout.write('='*80)
            self.stdout.write(self.style.ERROR(
                f'\nException Type: {type(e).__name__}'))
            self.stdout.write(self.style.ERROR(f'Exception Message: {str(e)}'))
            self.stdout.write(self.style.ERROR(f'Exception Args: {e.args}'))
            self.stdout.write(self.style.ERROR('\nFull Traceback:'))
            self.stdout.write(self.style.ERROR('─'*80))
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
            self.stdout.write(self.style.ERROR('─'*80))

        # Check what happened to the group and commitments
        self.stdout.write('\n🔍 POST-PROCESSING STATUS CHECK:')
        group.refresh_from_db()
        self.stdout.write(f'   Group status: {group.status}')
        self.stdout.write(
            f'   Group current_quantity: {group.current_quantity}')

        commitments_after = GroupCommitment.objects.filter(group=group)
        self.stdout.write(
            f'\n   Total commitments: {commitments_after.count()}')
        for commitment in commitments_after:
            self.stdout.write(
                f'   - Commitment {commitment.id}: status={commitment.status}')

        # Check if any orders were created - using commitments as a reference
        self.stdout.write(
            '\n   Checking for orders created from this group...')
        try:
            # Get all commitments for this group
            group_commitment_ids = list(GroupCommitment.objects.filter(
                group=group
            ).values_list('id', flat=True))

            if group_commitment_ids:
                # Import OrderItem here to avoid circular imports
                from apps.orders.models import OrderItem

                # Find orders that have items referencing these commitments
                orders_for_group = Order.objects.filter(
                    id__in=OrderItem.objects.filter(
                        group_commitment_id__in=group_commitment_ids
                    ).values_list('order_id', flat=True)
                ).distinct()

                self.stdout.write(
                    f'   Orders created for this group: {orders_for_group.count()}')
                for order in orders_for_group:
                    self.stdout.write(
                        f'   - Order {order.id}: {order.reference_number} | Status: {order.status} | Total: £{order.total}')
            else:
                self.stdout.write(
                    '   No commitments found, therefore no orders.')
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'   ⚠️  Could not check for orders: {str(e)}'))

        # Now test order creation directly for the first commitment
        self.stdout.write('\n' + '='*80)
        self.stdout.write('🧪 DIRECT ORDER CREATION TEST')
        self.stdout.write('='*80 + '\n')

        # Get first commitment (any status)
        test_commitment = GroupCommitment.objects.filter(
            group=group
        ).select_related('buyer', 'delivery_address').first()

        if not test_commitment:
            self.stdout.write(self.style.WARNING(
                '⚠️  No commitments found to test'))
        else:
            self.stdout.write(
                f'📝 Testing with Commitment {test_commitment.id}:')
            self.stdout.write(f'   Status: {test_commitment.status}')
            self.stdout.write(
                f'   Buyer: {test_commitment.buyer.username} (ID: {test_commitment.buyer.id})')
            self.stdout.write(f'   Quantity: {test_commitment.quantity}')
            self.stdout.write(
                f'   Payment Intent: {test_commitment.stripe_payment_intent_id}')
            self.stdout.write(
                f'   Delivery Address: {test_commitment.delivery_address}')

            if test_commitment.delivery_address:
                addr = test_commitment.delivery_address
                self.stdout.write(f'   Address Details:')
                self.stdout.write(f'      ID: {addr.id}')
                self.stdout.write(f'      User: {addr.user.username}')
                self.stdout.write(f'      Name: {addr.address_name}')
                self.stdout.write(f'      Full: {addr.city}, {addr.postcode}')
            else:
                self.stdout.write(self.style.ERROR(
                    '   ❌ NO DELIVERY ADDRESS - THIS WILL CAUSE ORDER CREATION TO FAIL'))

            if test_commitment.status == 'pending':
                self.stdout.write(
                    '\n📝 Attempting to create order from pending commitment...')
                self.stdout.write(f'   Group ID: {group.id}')
                self.stdout.write(f'   Commitment ID: {test_commitment.id}')

                order_service = OrderService()
                self.stdout.write(f'   OrderService instance: {order_service}')

                try:
                    self.stdout.write(
                        '\n🚀 Calling order_service.create_order_from_group()...')

                    result = order_service.create_order_from_group(
                        group_id=group.id,
                        commitment_id=test_commitment.id
                    )

                    self.stdout.write(f'\n📬 Result received:')
                    self.stdout.write(f'   Type: {type(result)}')
                    self.stdout.write(f'   Success: {result.success}')

                    if result.success:
                        self.stdout.write(self.style.SUCCESS(
                            '\n✅ ORDER CREATED SUCCESSFULLY!'))
                        order = result.data
                        self.stdout.write(f'   Order object: {order}')
                        self.stdout.write(f'   Order ID: {order.id}')
                        self.stdout.write(
                            f'   Reference: {order.reference_number}')
                        self.stdout.write(f'   Total: £{order.total}')
                        self.stdout.write(f'   Status: {order.status}')
                        self.stdout.write(f'   Buyer: {order.buyer.username}')
                        self.stdout.write(
                            f'   Vendor: {order.vendor.business_name}')
                        self.stdout.write(
                            f'   Items count: {order.items.count()}')

                        for item in order.items.all():
                            self.stdout.write(
                                f'      - {item.product.name}: {item.quantity} x £{item.price}')
                    else:
                        self.stdout.write(self.style.ERROR(
                            '\n❌ ORDER CREATION FAILED'))
                        self.stdout.write(self.style.ERROR(
                            f'   Error: {result.error}'))
                        self.stdout.write(self.style.ERROR(
                            f'   Error Code: {result.error_code}'))

                        # Try to get more details
                        if hasattr(result, 'metadata') and result.metadata:
                            self.stdout.write(self.style.ERROR(
                                f'   Metadata: {result.metadata}'))

                        if hasattr(result, 'data') and result.data:
                            self.stdout.write(self.style.ERROR(
                                f'   Data: {result.data}'))

                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f'\n❌ EXCEPTION DURING ORDER CREATION'))
                    self.stdout.write(self.style.ERROR('='*80))
                    self.stdout.write(self.style.ERROR(
                        f'Type: {type(e).__name__}'))
                    self.stdout.write(self.style.ERROR(
                        f'Message: {str(e)}'))
                    self.stdout.write(self.style.ERROR(
                        f'Args: {e.args}'))

                    # Print full exception info
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    self.stdout.write(self.style.ERROR(
                        '\nDetailed Exception Info:'))
                    self.stdout.write(self.style.ERROR('─'*80))
                    for line in traceback.format_exception(exc_type, exc_value, exc_traceback):
                        self.stdout.write(self.style.ERROR(line.rstrip()))
                    self.stdout.write(self.style.ERROR('─'*80))

                    # Additional debugging info
                    self.stdout.write(self.style.ERROR(
                        '\nDebugging Variables:'))
                    self.stdout.write(self.style.ERROR(
                        f'   group_id type: {type(group.id)}'))
                    self.stdout.write(self.style.ERROR(
                        f'   group_id value: {group.id}'))
                    self.stdout.write(self.style.ERROR(
                        f'   commitment_id type: {type(test_commitment.id)}'))
                    self.stdout.write(self.style.ERROR(
                        f'   commitment_id value: {test_commitment.id}'))

            else:
                self.stdout.write(
                    f'\nℹ️  Commitment already processed (status: {test_commitment.status})')
                self.stdout.write('   Skipping direct order creation test')

        # Restore original state
        self.stdout.write(f'\n🔄 RESTORING ORIGINAL STATE:')
        self.stdout.write(f'   Restoring expires_at to: {original_expiry}')
        self.stdout.write(f'   Restoring status to: {original_status}')

        group.expires_at = original_expiry
        group.status = original_status
        group.save(update_fields=['expires_at', 'status'])

        # Reset commitment statuses
        updated_count = GroupCommitment.objects.filter(
            group=group).update(status='pending')
        self.stdout.write(f'   Reset {updated_count} commitments to pending')

        # Verify restoration
        group.refresh_from_db()
        self.stdout.write(
            f'   ✅ Verified group expires_at: {group.expires_at}')
        self.stdout.write(f'   ✅ Verified group status: {group.status}')

        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.SUCCESS('✅ VERBOSE TEST COMPLETE'))
        self.stdout.write('='*80 + '\n')
