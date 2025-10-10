"""
Unit tests for buying groups Celery tasks.
Tests group expiration, notifications, and cleanup operations.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.utils import timezone
from django.db import models

from apps.buying_groups.tasks import (
    process_expired_buying_groups,
    check_group_thresholds,
    notify_expiring_groups,
    cleanup_old_group_updates
)
from apps.buying_groups.models import BuyingGroup, GroupCommitment, GroupUpdate
from tests.conftest import (
    VendorFactory,
    ProductFactory,
    BuyingGroupFactory,
    GroupCommitmentFactory,
    UserFactory
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

        result = process_expired_buying_groups()

        successful_group.refresh_from_db()
        assert successful_group.status == 'active'
        assert result == {
            'processed': 1,
            'successful': 1,
            'failed': 0
        }

    def test_process_expired_groups_failure(self):
        """Test processing groups that failed to reach minimum."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        failed_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=45,  # Below minimum
            expires_at=timezone.now() - timedelta(hours=1)
        )

        result = process_expired_buying_groups()

        failed_group.refresh_from_db()
        assert failed_group.status == 'failed'
        assert result == {
            'processed': 1,
            'successful': 0,
            'failed': 1
        }

    def test_process_expired_groups_mixed_results(self):
        """Test processing mix of successful and failed groups."""
        vendor = VendorFactory(is_approved=True)
        product1 = ProductFactory(vendor=vendor, stock_quantity=100)
        product2 = ProductFactory(vendor=vendor, stock_quantity=100)

        # Successful group
        successful_group = BuyingGroupFactory(
            product=product1,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=70,
            expires_at=timezone.now() - timedelta(hours=1)
        )

        # Failed group
        failed_group = BuyingGroupFactory(
            product=product2,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=30,
            expires_at=timezone.now() - timedelta(hours=2)
        )

        result = process_expired_buying_groups()

        successful_group.refresh_from_db()
        failed_group.refresh_from_db()

        assert successful_group.status == 'active'
        assert failed_group.status == 'failed'
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

            # The task should raise the exception
            with pytest.raises(Exception, match="Database error"):
                process_expired_buying_groups()


@pytest.mark.django_db
class TestCheckGroupThresholds:
    """Test group threshold checking and notifications."""

    def test_check_50_percent_threshold(self):
        """Test notification when group reaches 50% of target."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,  # Exactly 50%
            expires_at=timezone.now() + timedelta(days=7)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

            # Should broadcast 50% threshold
            mock_broadcast.assert_called_once_with(
                group_id=group.id,
                threshold_percent=50,
                current_quantity=50,
                target_quantity=100
            )

        # Should create threshold update record
        threshold_updates = GroupUpdate.objects.filter(
            group=group,
            event_type='threshold'
        )
        assert threshold_updates.count() == 1
        assert '50%' in str(threshold_updates.first().event_data)

    def test_check_80_percent_threshold(self):
        """Test notification when group reaches 80% of target."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=80,  # Exactly 80%
            expires_at=timezone.now() + timedelta(days=7)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

            # Should broadcast both 50% and 80% thresholds
            assert mock_broadcast.call_count == 2

        # Should create two threshold update records
        threshold_updates = GroupUpdate.objects.filter(
            group=group,
            event_type='threshold'
        )
        assert threshold_updates.count() == 2

    def test_no_duplicate_threshold_notifications(self):
        """Test that threshold notifications are not duplicated."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,
            expires_at=timezone.now() + timedelta(days=7)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            # First check - should notify
            check_group_thresholds()
            assert mock_broadcast.call_count == 1

            # Second check - should not notify again
            mock_broadcast.reset_mock()
            check_group_thresholds()
            assert mock_broadcast.call_count == 0

    def test_check_thresholds_for_multiple_groups(self):
        """Test checking thresholds for multiple groups."""
        vendor = VendorFactory(is_approved=True)
        product1 = ProductFactory(vendor=vendor, stock_quantity=100)
        product2 = ProductFactory(vendor=vendor, stock_quantity=100)

        # Group at 50%
        group1 = BuyingGroupFactory(
            product=product1,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,
            expires_at=timezone.now() + timedelta(days=7)
        )

        # Group at 80%
        group2 = BuyingGroupFactory(
            product=product2,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=80,
            expires_at=timezone.now() + timedelta(days=7)
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_threshold_reached') as mock_broadcast:
            check_group_thresholds()

            # Group1: 1 notification (50%)
            # Group2: 2 notifications (50% and 80%)
            assert mock_broadcast.call_count == 3


@pytest.mark.django_db
class TestNotifyExpiringGroups:
    """Test expiring group notifications."""

    def test_notify_groups_expiring_within_24_hours(self):
        """Test notification for groups expiring in next 24 hours."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        # Group expiring in 12 hours
        expiring_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,
            expires_at=timezone.now() + timedelta(hours=12)
        )

        # Create a commitment so notification will be sent
        GroupCommitmentFactory(
            group=expiring_group,
            quantity=10,
            status='pending'
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

            assert result['groups_expiring'] == 1
            mock_broadcast.assert_called_once()

    def test_no_notification_for_groups_expiring_later(self):
        """Test no notification for groups expiring after 24 hours."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        # Group expiring in 48 hours
        future_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,
            expires_at=timezone.now() + timedelta(hours=48)
        )

        GroupCommitmentFactory(
            group=future_group,
            quantity=10,
            status='pending'
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

            assert result['groups_expiring'] == 0
            mock_broadcast.assert_not_called()

    def test_no_notification_for_already_expired_groups(self):
        """Test no notification for groups that already expired."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        # Already expired group
        expired_group = BuyingGroupFactory(
            product=product,
            status='open',
            target_quantity=100,
            min_quantity=60,
            current_quantity=50,
            expires_at=timezone.now() - timedelta(hours=1)
        )

        GroupCommitmentFactory(
            group=expired_group,
            quantity=10,
            status='pending'
        )

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

            assert result['groups_expiring'] == 0
            mock_broadcast.assert_not_called()

    def test_notify_multiple_expiring_groups(self):
        """Test notification for multiple expiring groups."""
        vendor = VendorFactory(is_approved=True)
        product1 = ProductFactory(vendor=vendor, stock_quantity=100)
        product2 = ProductFactory(vendor=vendor, stock_quantity=100)

        # Two groups expiring in next 24 hours
        group1 = BuyingGroupFactory(
            product=product1,
            status='open',
            expires_at=timezone.now() + timedelta(hours=12)
        )
        group2 = BuyingGroupFactory(
            product=product2,
            status='open',
            expires_at=timezone.now() + timedelta(hours=18)
        )

        # Add commitments
        GroupCommitmentFactory(group=group1, quantity=10, status='pending')
        GroupCommitmentFactory(group=group2, quantity=15, status='pending')

        with patch('apps.core.utils.websocket_utils.broadcaster.broadcast_status_change') as mock_broadcast:
            result = notify_expiring_groups()

            assert result['groups_expiring'] == 2
            assert mock_broadcast.call_count == 2


@pytest.mark.django_db
class TestCleanupOldGroupUpdates:
    """Test cleanup of old group update records."""

    def test_cleanup_old_updates(self):
        """Test deletion of updates older than 30 days."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open'
        )

        # Create old updates (35 days ago)
        old_date = timezone.now() - timedelta(days=35)
        old_updates = []
        for i in range(5):
            update = GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={'quantity': 10}
            )
            # Manually update created_at to be old
            GroupUpdate.objects.filter(
                pk=update.pk).update(created_at=old_date)
            old_updates.append(update)

        # Create recent updates (10 days ago) - should not be deleted
        recent_date = timezone.now() - timedelta(days=10)
        recent_updates = []
        for i in range(3):
            update = GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={'quantity': 5}
            )
            GroupUpdate.objects.filter(
                pk=update.pk).update(created_at=recent_date)
            recent_updates.append(update)

        # Run cleanup
        result = cleanup_old_group_updates()

        assert result['deleted'] == 5

        # Verify old updates deleted
        for update in old_updates:
            assert not GroupUpdate.objects.filter(pk=update.pk).exists()

        # Verify recent updates retained
        for update in recent_updates:
            assert GroupUpdate.objects.filter(pk=update.pk).exists()

    def test_cleanup_handles_no_old_updates(self):
        """Test cleanup when there are no old updates."""
        vendor = VendorFactory(is_approved=True)
        product = ProductFactory(vendor=vendor, stock_quantity=100)

        group = BuyingGroupFactory(
            product=product,
            status='open'
        )

        # Create only recent updates
        for _ in range(3):
            GroupUpdate.objects.create(
                group=group,
                event_type='commitment',
                event_data={'quantity': 10}
            )

        result = cleanup_old_group_updates()

        assert result['deleted'] == 0
        assert GroupUpdate.objects.count() == 3

    def test_cleanup_handles_errors_gracefully(self):
        """Test error handling in cleanup task."""
        with patch('apps.buying_groups.models.GroupUpdate.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            with pytest.raises(Exception, match="Database error"):
                cleanup_old_group_updates()
