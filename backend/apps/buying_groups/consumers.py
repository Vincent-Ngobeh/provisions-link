"""
WebSocket consumer for real-time group buying updates.
Handles progress tracking, participant counts, and status changes.
"""
import json
import logging
from typing import Dict, Any
from decimal import Decimal
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone

logger = logging.getLogger(__name__)


class GroupBuyingConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for group buying real-time updates.

    Message Types:
    - subscribe: Join a group buying room
    - unsubscribe: Leave a group buying room
    - ping: Keep-alive message
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_id = None
        self.group_room_name = None
        self.user = None

    async def connect(self):
        """
        Accept WebSocket connection if user is authenticated via JWT.
        """
        # Extract token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        token = None

        if query_string:
            params = parse_qs(query_string)
            token = params.get('token', [None])[0]

        # If no token provided, reject connection
        if not token:
            logger.warning("WebSocket connection rejected: No token provided")
            await self.close(code=4001)
            return

        # Validate JWT token and get user
        try:
            user_id = await self.validate_token(token)
            if user_id:
                self.user = await self.get_user(user_id)

            if not self.user:
                logger.warning(
                    f"WebSocket connection rejected: Invalid token or user not found")
                await self.close(code=4001)
                return

        except Exception as e:
            logger.error(f"WebSocket authentication failed: {e}")
            await self.close(code=4001)
            return

        # Accept the connection
        await self.accept()

        # Send initial connection success
        await self.send_json({
            'type': 'connection_established',
            'data': {
                'message': 'Connected to group buying updates',
                'authenticated': True,
                'user_id': self.user.id,
                'username': self.user.username
            }
        })

        logger.info(
            f"WebSocket connection established for user: {self.user.id}")

    async def disconnect(self, close_code):
        """
        Clean up when WebSocket disconnects.
        """
        # Leave group room if joined
        if self.group_room_name:
            await self.channel_layer.group_discard(
                self.group_room_name,
                self.channel_name
            )
            logger.info(
                f"User {self.user.id if self.user else 'Unknown'} left group room: {self.group_room_name}"
            )

    async def receive_json(self, content, **kwargs):
        """
        Handle incoming WebSocket messages.
        """
        message_type = content.get('type')

        if message_type == 'subscribe':
            await self.handle_subscribe(content)
        elif message_type == 'unsubscribe':
            await self.handle_unsubscribe(content)
        elif message_type == 'ping':
            await self.send_json({'type': 'pong'})
        else:
            await self.send_json({
                'type': 'error',
                'data': {'message': f'Unknown message type: {message_type}'}
            })

    async def handle_subscribe(self, content):
        """
        Subscribe to a group buying room for updates.
        """
        new_group_id = content.get('group_id')

        if not new_group_id:
            await self.send_json({
                'type': 'error',
                'data': {'message': 'Group ID required'}
            })
            return

        # Leave previous group if any
        if self.group_room_name:
            await self.channel_layer.group_discard(
                self.group_room_name,
                self.channel_name
            )

        # Join new group room
        self.group_id = new_group_id
        self.group_room_name = f'group_buying_{new_group_id}'

        await self.channel_layer.group_add(
            self.group_room_name,
            self.channel_name
        )

        # Send current group state
        group_data = await self.get_group_data(new_group_id)

        if group_data:
            await self.send_json({
                'type': 'subscribed',
                'data': {
                    'group_id': new_group_id,
                    'current_state': group_data
                }
            })
            logger.info(
                f"User {self.user.id} subscribed to group {new_group_id}")
        else:
            await self.send_json({
                'type': 'error',
                'data': {'message': 'Group not found'}
            })
            self.group_id = None
            self.group_room_name = None

    async def handle_unsubscribe(self, content):
        """
        Unsubscribe from current group.
        """
        if self.group_room_name:
            await self.channel_layer.group_discard(
                self.group_room_name,
                self.channel_name
            )

            await self.send_json({
                'type': 'unsubscribed',
                'data': {'group_id': self.group_id}
            })

            logger.info(
                f"User {self.user.id} unsubscribed from group {self.group_id}"
            )

            self.group_id = None
            self.group_room_name = None

    # Channel layer message handlers

    async def group_progress(self, event):
        """
        Send progress update to WebSocket client.
        """
        await self.send_json({
            'type': 'progress_update',
            'data': event['data']
        })

    async def group_threshold(self, event):
        """
        Send threshold reached notification.
        """
        await self.send_json({
            'type': 'threshold_reached',
            'data': event['data']
        })

    async def group_status_change(self, event):
        """
        Send status change notification.
        """
        await self.send_json({
            'type': 'status_change',
            'data': event['data']
        })

    async def group_commitment(self, event):
        """
        Send new commitment notification.
        """
        await self.send_json({
            'type': 'new_commitment',
            'data': event['data']
        })

    async def group_cancelled(self, event):
        """
        Send cancellation notification.
        """
        await self.send_json({
            'type': 'commitment_cancelled',
            'data': event['data']
        })

    # Database access methods

    @database_sync_to_async
    def validate_token(self, token: str) -> int:
        """
        Validate JWT token and return user ID.

        Args:
            token: JWT access token

        Returns:
            User ID if token is valid, None otherwise
        """
        try:
            from rest_framework_simplejwt.tokens import AccessToken

            access_token = AccessToken(token)
            user_id = access_token.get('user_id')

            return user_id

        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None

    @database_sync_to_async
    def get_user(self, user_id: int):
        """
        Fetch user from database.

        Args:
            user_id: User ID

        Returns:
            User object or None
        """
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.get(id=user_id)
        except Exception as e:
            logger.warning(f"User {user_id} not found: {e}")
            return None

    @database_sync_to_async
    def get_group_data(self, group_id: int) -> Dict[str, Any]:
        """
        Fetch current group state from database.
        """
        from apps.buying_groups.models import BuyingGroup

        try:
            group = BuyingGroup.objects.select_related('product__vendor').get(
                id=group_id
            )

            # Calculate time remaining
            time_remaining = group.time_remaining
            time_remaining_seconds = int(
                time_remaining.total_seconds()) if time_remaining else 0

            return {
                'group_id': group.id,
                'product_name': group.product.name,
                'vendor_name': group.product.vendor.business_name,
                'current_quantity': group.current_quantity,
                'target_quantity': group.target_quantity,
                'min_quantity': group.min_quantity,
                'progress_percent': float(group.progress_percent),
                'participants_count': group.commitments.filter(status='pending').count(),
                'time_remaining_seconds': time_remaining_seconds,
                'status': group.status,
                'discount_percent': float(group.discount_percent),
                'savings_per_unit': float(group.savings_per_unit),
                'area_name': group.area_name,
                'expires_at': group.expires_at.isoformat()
            }
        except BuyingGroup.DoesNotExist:
            logger.warning(f"Group {group_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error fetching group data: {e}")
            return None
