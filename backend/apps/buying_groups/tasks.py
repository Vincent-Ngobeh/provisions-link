"""
Celery tasks for buying group operations.
Handles periodic processing of groups and notifications.
"""
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(name='process_expired_buying_groups')
def process_expired_buying_groups():
    """
    Process all expired buying groups and update their status.
    Runs hourly via Celery Beat.
    """
    from apps.buying_groups.models import BuyingGroup
    from apps.buying_groups.services.group_buying_service import GroupBuyingService

    service = GroupBuyingService()

    try:
        # Find all expired open groups
        expired_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__lte=timezone.now()
        )

        count = expired_groups.count()
        logger.info(f"Processing {count} expired groups")

        # Process each group
        stats = service.process_expired_groups()

        logger.info(
            f"Processed expired groups - "
            f"Total: {stats['total_processed']}, "
            f"Successful: {stats['successful']}, "
            f"Failed: {stats['failed']}"
        )

        # Return with consistent key naming matching what tests expect
        return {
            'processed': stats['total_processed'],
            'successful': stats['successful'],
            'failed': stats['failed']
        }

    except Exception as e:
        logger.error(f"Error processing expired groups: {str(e)}")
        raise


@shared_task(name='process_successful_group_orders')
def process_successful_group_orders(group_id):
    """
    Create orders for all commitments in a successful buying group.
    Called when a group reaches its target or minimum quantity.

    Args:
        group_id: ID of the successful buying group
    """
    from apps.orders.services.order_service import OrderService

    service = OrderService()

    try:
        logger.info(f"Processing orders for successful group {group_id}")

        result = service.create_orders_from_successful_group(group_id)

        if result.success:
            logger.info(
                f"Created {result.data['orders_created']} orders for group {group_id}"
            )
            return result.data
        else:
            logger.error(f"Failed to process group {group_id}: {result.error}")
            raise Exception(result.error)

    except Exception as e:
        logger.error(f"Error processing group orders: {str(e)}")
        raise


@shared_task(name='check_group_thresholds')
def check_group_thresholds():
    """
    Check all active groups for threshold milestones.
    Sends notifications when groups reach 50%, 80%, etc.
    Runs every 30 minutes.
    """
    from apps.buying_groups.models import BuyingGroup, GroupUpdate
    from apps.core.utils.websocket_utils import broadcaster

    try:
        active_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now()
        )

        for group in active_groups:
            progress = group.progress_percent

            # Check if we've already notified for this threshold
            existing_threshold_updates = GroupUpdate.objects.filter(
                group=group,
                event_type='threshold'
            ).values_list('event_data', flat=True)

            # Check 80% threshold FIRST (higher thresholds first)
            # This ensures both thresholds can be triggered independently
            if progress >= 80 and not any('80%' in str(update) for update in existing_threshold_updates):
                broadcaster.broadcast_threshold_reached(
                    group_id=group.id,
                    threshold_percent=80,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity
                )

                GroupUpdate.objects.create(
                    group=group,
                    event_type='threshold',
                    event_data={'milestone': '80%',
                                'quantity': group.current_quantity}
                )

                logger.info(f"Group {group.id} reached 80% threshold")

            # Check 50% threshold (separate if, not elif)
            if progress >= 50 and not any('50%' in str(update) for update in existing_threshold_updates):
                broadcaster.broadcast_threshold_reached(
                    group_id=group.id,
                    threshold_percent=50,
                    current_quantity=group.current_quantity,
                    target_quantity=group.target_quantity
                )

                GroupUpdate.objects.create(
                    group=group,
                    event_type='threshold',
                    event_data={'milestone': '50%',
                                'quantity': group.current_quantity}
                )

                logger.info(f"Group {group.id} reached 50% threshold")

    except Exception as e:
        logger.error(f"Error checking group thresholds: {str(e)}")
        raise


@shared_task(name='notify_expiring_groups')
def notify_expiring_groups():
    """
    Send notifications for groups expiring within 24 hours.
    Runs every 6 hours via Celery Beat.
    """
    from apps.buying_groups.models import BuyingGroup
    from apps.core.utils.websocket_utils import broadcaster

    try:
        # Find groups expiring in the next 24 hours
        now = timezone.now()
        expiring_soon = now + timedelta(hours=24)

        expiring_groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=now,
            expires_at__lte=expiring_soon
        )

        count = 0
        for group in expiring_groups:
            # Only notify if there are commitments
            if group.commitments.filter(status='pending').exists():
                broadcaster.broadcast_status_change(
                    group_id=group.id,
                    old_status='open',
                    new_status='open',
                    reason='Group expires in less than 24 hours!'
                )
                count += 1

                logger.info(f"Notified group {group.id} - expiring soon")

        return {'groups_expiring': count}

    except Exception as e:
        logger.error(f"Error notifying expiring groups: {str(e)}")
        raise


@shared_task(name='cleanup_old_group_updates')
def cleanup_old_group_updates():
    """
    Clean up old GroupUpdate records to prevent database bloat.
    Keeps only last 30 days of updates.
    Runs weekly.
    """
    from apps.buying_groups.models import GroupUpdate

    try:
        # Delete updates older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        old_updates = GroupUpdate.objects.filter(created_at__lt=cutoff_date)

        count = old_updates.count()
        old_updates.delete()

        logger.info(f"Deleted {count} old group updates")

        return {'deleted': count}

    except Exception as e:
        logger.error(f"Error cleaning up group updates: {str(e)}")
        raise


@shared_task(name='refresh_demo_buying_groups')
def refresh_demo_buying_groups():
    """
    Automatically refresh failed demo buying groups.
    Gives failed groups a "second chance" by resetting them to open status
    with a new expiry date.

    Only refreshes groups that:
    - Are demo groups (area_name starts with [DEMO])
    - Have status='failed' (didn't reach minimum quantity)

    Leaves successful groups alone to complete their natural lifecycle.
    Runs daily via Celery Beat.
    """
    from apps.buying_groups.models import BuyingGroup, GroupCommitment
    import random

    try:
        # Find failed demo groups
        failed_demo_groups = BuyingGroup.objects.filter(
            area_name__startswith='[DEMO]',
            status='failed'
        )

        count = failed_demo_groups.count()

        if count == 0:
            logger.info("No failed demo groups to refresh")
            return {
                'refreshed': 0,
                'message': 'No failed demo groups found'
            }

        logger.info(f"Refreshing {count} failed demo groups")

        refreshed_count = 0

        for group in failed_demo_groups:
            # Random 7-14 days for variety
            extension_days = random.randint(7, 14)
            new_expiry = timezone.now() + timedelta(days=extension_days)

            # Reset to 30-50% progress for a fresh start
            progress_ratio = random.uniform(0.30, 0.50)
            new_quantity = int(group.target_quantity * progress_ratio)

            # Update the group
            group.expires_at = new_expiry
            group.status = 'open'
            group.current_quantity = new_quantity
            group.last_update_at = timezone.now()
            group.save(update_fields=[
                'expires_at', 'status', 'current_quantity', 'last_update_at'
            ])

            # Reset cancelled commitments to pending
            GroupCommitment.objects.filter(
                group=group,
                status='cancelled'
            ).update(status='pending')

            refreshed_count += 1

            logger.info(
                f"Refreshed group {group.id} ({group.product.name}) - "
                f"new expiry: {new_expiry.strftime('%Y-%m-%d')}, "
                f"progress reset to {new_quantity}/{group.target_quantity}"
            )

        logger.info(f"Successfully refreshed {refreshed_count} demo groups")

        return {
            'refreshed': refreshed_count,
            'message': f'Refreshed {refreshed_count} failed demo groups'
        }

    except Exception as e:
        logger.error(f"Error refreshing demo groups: {str(e)}")
        raise
