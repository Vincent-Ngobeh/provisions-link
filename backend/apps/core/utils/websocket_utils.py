"""
WebSocket utility functions for broadcasting events.
Used by services to send real-time updates.
"""
import logging
from typing import Dict, Any, Optional
from decimal import Decimal

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.serializers.json import DjangoJSONEncoder
import json

logger = logging.getLogger(__name__)


class GroupBuyingBroadcaster:
    """
    Utility class for broadcasting group buying events via WebSockets.
    """

    def __init__(self):
        self.channel_layer = get_channel_layer()

    def _get_room_name(self, group_id: int) -> str:
        """Get the room name for a group."""
        return f'group_buying_{group_id}'

    def _send_to_group(self, group_id: int, event_type: str, data: Dict[str, Any]):
        """
        Send a message to all clients in a group room.

        Args:
            group_id: The buying group ID
            event_type: The type of event (e.g., 'group_progress')
            data: The data to send
        """
        try:
            room_name = self._get_room_name(group_id)

            # Convert Decimal to float for JSON serialization
            data = self._prepare_data_for_json(data)

            async_to_sync(self.channel_layer.group_send)(
                room_name,
                {
                    'type': event_type,
                    'data': data
                }
            )

            logger.debug(f"Sent {event_type} to room {room_name}")

        except Exception as e:
            logger.error(f"Error broadcasting to group {group_id}: {e}")

    def _prepare_data_for_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare data for JSON serialization.
        Converts Decimal to float and handles other non-serializable types.
        """
        prepared = {}
        for key, value in data.items():
            if isinstance(value, Decimal):
                prepared[key] = float(value)
            elif hasattr(value, 'isoformat'):  # datetime objects
                prepared[key] = value.isoformat()
            else:
                prepared[key] = value
        return prepared

    def broadcast_progress(
        self,
        group_id: int,
        current_quantity: int,
        target_quantity: int,
        participants_count: int,
        progress_percent: float,
        time_remaining_seconds: Optional[int] = None
    ):
        """
        Broadcast a progress update for a group.

        Args:
            group_id: The buying group ID
            current_quantity: Current quantity committed
            target_quantity: Target quantity for the group
            participants_count: Number of participants
            progress_percent: Progress percentage (0-100)
            time_remaining_seconds: Seconds until group expires
        """
        data = {
            'group_id': group_id,
            'current_quantity': current_quantity,
            'target_quantity': target_quantity,
            'participants_count': participants_count,
            'progress_percent': progress_percent,
        }

        if time_remaining_seconds is not None:
            data['time_remaining_seconds'] = time_remaining_seconds

        self._send_to_group(group_id, 'group.progress', data)

    def broadcast_threshold_reached(
        self,
        group_id: int,
        threshold_percent: float,
        current_quantity: int,
        target_quantity: int
    ):
        """
        Broadcast that a group has reached a threshold (e.g., 80%).

        Args:
            group_id: The buying group ID
            threshold_percent: The threshold reached (e.g., 80)
            current_quantity: Current quantity committed
            target_quantity: Target quantity for the group
        """
        data = {
            'group_id': group_id,
            'threshold_percent': threshold_percent,
            'current_quantity': current_quantity,
            'target_quantity': target_quantity,
            'message': f'Group has reached {threshold_percent}% of target!'
        }

        self._send_to_group(group_id, 'group.threshold', data)

    def broadcast_status_change(
        self,
        group_id: int,
        old_status: str,
        new_status: str,
        reason: Optional[str] = None
    ):
        """
        Broadcast a status change for a group.

        Args:
            group_id: The buying group ID
            old_status: Previous status
            new_status: New status
            reason: Optional reason for the change
        """
        data = {
            'group_id': group_id,
            'old_status': old_status,
            'new_status': new_status,
        }

        if reason:
            data['reason'] = reason

        # Set appropriate message based on status
        if new_status == 'active':
            data['message'] = 'Group buying is now active! Target reached!'
        elif new_status == 'completed':
            data['message'] = 'Group buying completed successfully!'
        elif new_status == 'failed':
            data['message'] = 'Group buying failed to reach minimum quantity.'
        elif new_status == 'cancelled':
            data['message'] = 'Group buying has been cancelled.'

        self._send_to_group(group_id, 'group.status_change', data)

    def broadcast_new_commitment(
        self,
        group_id: int,
        buyer_name: str,
        quantity: int,
        new_total: int,
        participants_count: int
    ):
        """
        Broadcast a new commitment to a group.

        Args:
            group_id: The buying group ID
            buyer_name: Name of the buyer (or 'Anonymous')
            quantity: Quantity committed
            new_total: New total quantity
            participants_count: Updated participant count
        """
        data = {
            'group_id': group_id,
            'buyer_name': buyer_name,
            'quantity': quantity,
            'new_total': new_total,
            'participants_count': participants_count,
            'message': f'{buyer_name} committed {quantity} units!'
        }

        self._send_to_group(group_id, 'group.commitment', data)

    def broadcast_commitment_cancelled(
        self,
        group_id: int,
        quantity: int,
        new_total: int,
        participants_count: int
    ):
        """
        Broadcast a cancelled commitment.

        Args:
            group_id: The buying group ID
            quantity: Quantity that was cancelled
            new_total: New total quantity
            participants_count: Updated participant count
        """
        data = {
            'group_id': group_id,
            'quantity': quantity,
            'new_total': new_total,
            'participants_count': participants_count,
            'message': f'A commitment of {quantity} units was cancelled.'
        }

        self._send_to_group(group_id, 'group.cancelled', data)


# Singleton instance for easy import
broadcaster = GroupBuyingBroadcaster()
