"""
Unit tests for buying group Celery tasks.
Tests periodic tasks for group processing, notifications, and cleanup.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call

from django.utils import timezone
from django.contrib.gis.geos import Point

from apps.buying_groups.tasks import (
    process_expired_buying_groups,
    check_group_thresholds,
    notify_expiring_groups,
    cleanup_old_group_updates
)
from apps.buying_groups.models import BuyingGroup, GroupCommitment, GroupUpdate
from tests.conftest import (
    BuyingGroupFactory,
    UserFactory,
    ProductFactory,
    VendorFactory,
    GroupCommitmentFactory
)


@pytest.mark.django_db
class TestProcessExpiredGroups:
    """Test processing of expired buying groups."""

    def test_process_expired_groups_success(self):
        """Test processing groups that reached minimum quantity."""
        # Create expired group that met minimum
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        successful_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=65,  # Above minimum
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Create commitments for the group
        for _ in range(3):
            GroupCommitmentFactory(
                group=successful_group,
                quantity=20,
                status='pending'
            )

        with patch('apps.buying_groups.tasks.logger') as mock_logger:
            result = process_expired_buying_groups()

        successful_group.refresh_from_db()
        assert successful_group.status == 'active'
        assert result == {
            'processed': 1,
            'successful': 1,
            'failed': 0
        }
        mock_logger.info.assert_called()

    def test_process_expired_groups_failure(self):
        """Test processing groups that didn't reach minimum quantity."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        failed_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=30,  # Below minimum
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Create insufficient commitments
        GroupCommitmentFactory(
            group=failed_group,
            quantity=30,
            status='pending',
            stripe_payment_intent_id='pi_test_123'
        )

        with patch('apps.integrations.services.stripe_service.StripeConnectService.cancel_payment_intent') as mock_cancel:
            mock_cancel.return_value.success = True
            result = process_expired_buying_groups()

        failed_group.refresh_from_db()
        assert failed_group.status == 'failed'
        assert result == {
            'processed': 1,
            'successful': 0,
            'failed': 1
        }

        # Verify Stripe payment was cancelled
        mock_cancel.assert_called_once_with('pi_test_123')

    def test_process_expired_groups_mixed_results(self):
        """Test processing multiple groups with different outcomes."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=200)

        # Successful group
        successful_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=50,
            min_quantity=30,
            current_quantity=35,
            expires_at=timezone.now() - timedelta(hours=2)
        )

        # Failed group
        failed_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=50,
            min_quantity=30,
            current_quantity=20,
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Not expired group (should not be processed)
        active_group = BuyingGroupFactory(
            product=product,
            status='open',
            expires_at=timezone.now() + timedelta(hours=1)
        )

        result = process_expired_buying_groups()

        successful_group.refresh_from_db()
        failed_group.refresh_from_db()
        active_group.refresh_from_db()

        assert successful_group.status == 'active'
        assert failed_group.status == 'failed'
        assert active_group.status == 'open'  # Unchanged

        assert result == {
            'processed': 2,
            'successful': 1,
            'failed': 1
        }

    def test_process_expired_groups_handles_errors(self):
        """Test error handling when processing fails."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            expires_at=timezone.now() - timedelta(hours=1)
        )

        with patch('apps.buying_groups.services.group_buying_service.GroupBuyingService.process_expired_groups') as mock_process:
            mock_process.side_effect = Exception("Database error")

            with patch('apps.buying_groups.tasks.logger') as mock_logger:
                # The task should raise the exception
                with pytest.raises(Exception, match="Database error"):
                    process_expired_buying_groups()

                mock_logger.error.assert_called()


@pytest.mark.django_db
class TestCheckGroupThresholds:
    """Test threshold checking for active groups."""

    def test_check_50_percent_threshold(self):
        """Test notification when group reaches 50% of target."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=50,  # Exactly 50%
            expires_at=timezone.now() + timedelta(days=3)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            with patch('apps.buying_groups.tasks.logger') as mock_logger:
                check_group_thresholds()

        # Should create threshold update
        threshold_update = GroupUpdate.objects.filter(
            group=group,
            event_type='threshold'
        ).first()

        assert threshold_update is not None
        assert '50%' in str(threshold_update.event_data)

        # Should broadcast
        mock_broadcast.assert_called_once_with(
            group_id=group.id,
            threshold_percent=50,
            current_quantity=50,
            target_quantity=100
        )

    def test_check_80_percent_threshold(self):
        """Test notification when group reaches 80% of target."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=80,  # Exactly 80%
            expires_at=timezone.now() + timedelta(days=2)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

        # Should create both 80% and 50% threshold updates
        threshold_updates = GroupUpdate.objects.filter(
            group=group,
            event_type='threshold'
        ).all()

        # Should have created both updates
        assert threshold_updates.count() == 2

        # Check that both milestones were recorded
        milestones = [update.event_data.get(
            'milestone') for update in threshold_updates]
        assert '80%' in milestones
        assert '50%' in milestones

        # Should broadcast twice (80% and 50%)
        assert mock_broadcast.call_count == 2

        # Verify both broadcasts
        calls = mock_broadcast.call_args_list
        thresholds_called = [call[1]['threshold_percent'] for call in calls]
        assert 80 in thresholds_called
        assert 50 in thresholds_called

    def test_no_duplicate_threshold_notifications(self):
        """Test that threshold notifications are not sent twice."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=80,
            expires_at=timezone.now() + timedelta(days=2)
        )

        # Create existing threshold updates for BOTH 80% and 50%
        GroupUpdate.objects.create(
            group=group,
            event_type='threshold',
            event_data={'milestone': '80%', 'quantity': 80}
        )
        GroupUpdate.objects.create(
            group=group,
            event_type='threshold',
            event_data={'milestone': '50%', 'quantity': 50}
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

        # Should not broadcast again since both thresholds are already recorded
        mock_broadcast.assert_not_called()

    def test_check_thresholds_for_multiple_groups(self):
        """Test checking thresholds for multiple active groups."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        # Group at 30% (no notification)
        group_30 = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=30,
            expires_at=timezone.now() + timedelta(days=3)
        )

        # Group at 55% (50% threshold only)
        group_55 = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=55,
            expires_at=timezone.now() + timedelta(days=3)
        )

        # Group at 85% (both 80% and 50% thresholds)
        group_85 = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            current_quantity=85,
            expires_at=timezone.now() + timedelta(days=3)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

        # Should broadcast 3 times total:
        # - group_55: 1 broadcast (50%)
        # - group_85: 2 broadcasts (80% and 50%)
        assert mock_broadcast.call_count == 3

        # Check which groups were notified
        call_args_list = mock_broadcast.call_args_list

        # Check group_55 got 50% notification
        group_55_calls = [
            call for call in call_args_list if call[1]['group_id'] == group_55.id]
        assert len(group_55_calls) == 1
        assert group_55_calls[0][1]['threshold_percent'] == 50

        # Check group_85 got both 80% and 50% notifications
        group_85_calls = [
            call for call in call_args_list if call[1]['group_id'] == group_85.id]
        assert len(group_85_calls) == 2
        thresholds = [call[1]['threshold_percent'] for call in group_85_calls]
        assert 80 in thresholds
        assert 50 in thresholds

        # Check group_30 got no notifications
        group_30_calls = [
            call for call in call_args_list if call[1]['group_id'] == group_30.id]
        assert len(group_30_calls) == 0


@pytest.mark.django_db
class TestNotifyExpiringGroups:
    """Test notifications for groups expiring soon."""

    def test_notify_groups_expiring_within_24_hours(self):
        """Test notification for groups expiring in next 24 hours."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        # Group expiring in 12 hours
        expiring_group = BuyingGroupFactory(
            product=product,
            status='open',
            expires_at=timezone.now() + timedelta(hours=12)
        )

        # Create commitments
        users = [UserFactory() for _ in range(3)]
        for user in users:
            GroupCommitmentFactory(
                group=expiring_group,
                buyer=user,
                status='pending'
            )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            with patch('apps.buying_groups.tasks.logger') as mock_logger:
                result = notify_expiring_groups()

        assert result['groups_expiring'] == 1

        # Should broadcast warning
        mock_broadcast.assert_called_once_with(
            group_id=expiring_group.id,
            old_status='open',
            new_status='open',
            reason='Group expires in less than 24 hours!'
        )

    def test_no_notification_for_groups_expiring_later(self):
        """Test no notification for groups expiring after 24 hours."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        # Group expiring in 2 days
        group = BuyingGroupFactory(
            product=product,
            status='open',
            expires_at=timezone.now() + timedelta(days=2)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

        assert result['groups_expiring'] == 0
        mock_broadcast.assert_not_called()

    def test_no_notification_for_already_expired_groups(self):
        """Test no notification for already expired groups."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        # Already expired group
        expired_group = BuyingGroupFactory(
            product=product,
            status='open',
            expires_at=timezone.now() - timedelta(hours=1)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

        assert result['groups_expiring'] == 0
        mock_broadcast.assert_not_called()

    def test_notify_multiple_expiring_groups(self):
        """Test notification for multiple groups expiring soon."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)

        # Create 3 groups expiring within 24 hours
        expiring_groups = []
        for hours in [6, 12, 23]:
            group = BuyingGroupFactory(
                product=product,
                status='open',
                expires_at=timezone.now() + timedelta(hours=hours)
            )
            expiring_groups.append(group)

            # Add commitments
            GroupCommitmentFactory(
                group=group,
                buyer=UserFactory(),
                status='pending'
            )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

        assert result['groups_expiring'] == 3
        assert mock_broadcast.call_count == 3


@pytest.mark.django_db
class TestCleanupOldGroupUpdates:
    """Test cleanup of old GroupUpdate records."""

    def test_cleanup_old_updates(self):
        """Test deletion of updates older than 30 days."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)
        group = BuyingGroupFactory(product=product)

        # Create old updates (should be deleted)
        old_updates = []
        for days_ago in [31, 45, 60]:
            update = GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={'test': 'data'},
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            # Force created_at to past date
            GroupUpdate.objects.filter(pk=update.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            old_updates.append(update)

        # Create recent updates (should be kept)
        recent_updates = []
        for days_ago in [1, 7, 15, 29]:
            update = GroupUpdate.objects.create(
                group=group,
                event_type='threshold',
                event_data={'test': 'data'}
            )
            GroupUpdate.objects.filter(pk=update.pk).update(
                created_at=timezone.now() - timedelta(days=days_ago)
            )
            recent_updates.append(update)

        result = cleanup_old_group_updates()

        # Check that old updates were deleted
        for update in old_updates:
            assert not GroupUpdate.objects.filter(pk=update.pk).exists()

        # Check that recent updates were kept
        for update in recent_updates:
            assert GroupUpdate.objects.filter(pk=update.pk).exists()

        assert result['deleted'] == 3

    def test_cleanup_handles_no_old_updates(self):
        """Test cleanup when there are no old updates."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor)
        group = BuyingGroupFactory(product=product)

        # Create only recent updates
        for _ in range(5):
            GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={'test': 'data'}
            )

        result = cleanup_old_group_updates()

        assert result['deleted'] == 0
        assert GroupUpdate.objects.count() == 5

    def test_cleanup_handles_errors_gracefully(self):
        """Test error handling in cleanup task."""
        with patch('apps.buying_groups.models.GroupUpdate.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            with patch('apps.buying_groups.tasks.logger') as mock_logger:
                with pytest.raises(Exception):
                    cleanup_old_group_updates()

                mock_logger.error.assert_called()
