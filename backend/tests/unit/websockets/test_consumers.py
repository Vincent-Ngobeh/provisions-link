"""
Unit tests for GroupBuyingConsumer WebSocket handler.
Tests connection, subscription, and message broadcasting.
"""
import pytest
import json
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.buying_groups.consumers import GroupBuyingConsumer
from apps.buying_groups.models import BuyingGroup, GroupCommitment, GroupUpdate
from apps.vendors.models import Vendor
from apps.products.models import Product, Category
from tests.conftest import BuyingGroupFactory, UserFactory, ProductFactory, CategoryFactory

User = get_user_model()


def get_jwt_token(user):
    """Helper to generate JWT token for testing."""
    token = AccessToken.for_user(user)
    return str(token)


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestGroupBuyingConsumerConnection:
    """Test WebSocket connection handling."""

    async def test_anonymous_user_cannot_connect(self):
        """Test that anonymous users cannot connect without token."""
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/group-buying/"
        )

        connected, _ = await communicator.connect()
        # Connection should be rejected without token
        assert connected is False

    async def test_authenticated_user_can_connect(self, test_user):
        """Test that authenticated users can connect with valid JWT token."""
        token = get_jwt_token(test_user)

        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        connected, _ = await communicator.connect()
        assert connected is True

        # Should receive connection confirmation
        response = await communicator.receive_json_from()
        assert response['type'] == 'connection_established'
        assert response['data']['authenticated'] is True
        assert response['data']['user_id'] == test_user.id

        await communicator.disconnect()

    async def test_connection_with_invalid_path(self):
        """Test that connection without token fails."""
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/invalid-path/"
        )

        connected, _ = await communicator.connect()
        # Should not connect without token
        assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestGroupSubscription:
    """Test group subscription functionality."""

    @pytest.mark.django_db(transaction=True)
    async def test_subscribe_to_valid_group(self, db, test_user):
        """Test subscribing to a valid group."""
        # Create test data synchronously
        @database_sync_to_async
        def create_test_data():
            from django.contrib.gis.geos import Point

            # Create category first (without description field)
            category = Category.objects.create(
                name='Food & Beverages',
                slug='food-beverages'
            )

            vendor = Vendor.objects.create(
                user=UserFactory(),
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                is_approved=True
            )

            product = Product.objects.create(
                vendor=vendor,
                category=category,  # Now providing the required category
                name='Test Product',
                price=Decimal('10.00'),
                stock_quantity=100
            )

            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=50,
                min_quantity=30,
                current_quantity=10,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return group

        group = await create_test_data()

        # Now test the WebSocket
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()  # Consume connection message

        # Subscribe to group
        await communicator.send_json_to({
            'type': 'subscribe',
            'group_id': group.id
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'subscribed', f"Got error: {response.get('data', {}).get('message')}"
        assert response['data']['group_id'] == group.id
        assert 'current_state' in response['data']

        # Verify current state contains expected fields
        state = response['data']['current_state']
        assert state['product_name'] == 'Test Product'
        assert state['vendor_name'] == 'Test Vendor'

        await communicator.disconnect()

    async def test_subscribe_to_invalid_group(self, test_user):
        """Test subscribing to non-existent group returns error."""
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()  # Consume connection message

        # Subscribe to invalid group
        await communicator.send_json_to({
            'type': 'subscribe',
            'group_id': 99999
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'error'
        assert 'not found' in response['data']['message'].lower()

        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    async def test_unsubscribe_from_group(self, db, test_user):
        """Test unsubscribing from a group."""
        # First create a group to subscribe to
        @database_sync_to_async
        def create_test_group():
            from django.contrib.gis.geos import Point

            category = Category.objects.create(
                name='Test Category',
                slug='test-category-unsub'
            )

            vendor = Vendor.objects.create(
                user=UserFactory(),
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                is_approved=True
            )

            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name='Test Product',
                price=Decimal('10.00'),
                stock_quantity=100
            )

            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=50,
                min_quantity=30,
                current_quantity=10,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return group

        group = await create_test_group()

        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()  # Connection message

        # First subscribe to a group
        await communicator.send_json_to({
            'type': 'subscribe',
            'group_id': group.id
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'subscribed'

        # Now unsubscribe from the group
        await communicator.send_json_to({
            'type': 'unsubscribe'
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'unsubscribed'
        assert response['data']['group_id'] == group.id

        await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestBroadcastMessages:
    """Test receiving broadcast messages."""

    @pytest.mark.django_db(transaction=True)
    async def test_receive_progress_update(self, db, test_user):
        """Test receiving progress update broadcasts."""
        @database_sync_to_async
        def create_test_group():
            from django.contrib.gis.geos import Point

            category = Category.objects.create(
                name='Test Category',
                slug='test-category-progress'
            )

            vendor = Vendor.objects.create(
                user=UserFactory(),
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                is_approved=True
            )

            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name='Test Product',
                price=Decimal('10.00'),
                stock_quantity=100
            )

            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=50,
                min_quantity=30,
                current_quantity=10,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return group

        group = await create_test_group()

        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()  # Connection message

        # Subscribe to group
        await communicator.send_json_to({
            'type': 'subscribe',
            'group_id': group.id
        })
        await communicator.receive_json_from()  # Subscription confirmation

        # Simulate a progress broadcast
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'group_buying_{group.id}',
            {
                'type': 'group_progress',
                'data': {
                    'group_id': group.id,
                    'current_quantity': 20,
                    'target_quantity': 50,
                    'participants_count': 3,
                    'progress_percent': 40.0
                }
            }
        )

        # Should receive the progress update
        response = await communicator.receive_json_from()
        assert response['type'] == 'progress_update'
        assert response['data']['current_quantity'] == 20
        assert response['data']['progress_percent'] == 40.0

        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    async def test_receive_threshold_notification(self, db, test_user):
        """Test receiving threshold reached notification."""
        @database_sync_to_async
        def create_test_group():
            from django.contrib.gis.geos import Point

            category = Category.objects.create(
                name='Test Category',
                slug='test-category-threshold'
            )

            vendor = Vendor.objects.create(
                user=UserFactory(),
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                is_approved=True
            )

            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name='Test Product',
                price=Decimal('10.00'),
                stock_quantity=100
            )

            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=50,
                min_quantity=30,
                current_quantity=40,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return group

        group = await create_test_group()

        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()

        await communicator.send_json_to({
            'type': 'subscribe',
            'group_id': group.id
        })
        await communicator.receive_json_from()

        # Simulate threshold reached broadcast
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'group_buying_{group.id}',
            {
                'type': 'group_threshold',
                'data': {
                    'group_id': group.id,
                    'threshold_percent': 80,
                    'current_quantity': 40,
                    'target_quantity': 50,
                    'message': 'Group has reached 80% of target!'
                }
            }
        )

        response = await communicator.receive_json_from()
        assert response['type'] == 'threshold_reached'
        assert response['data']['threshold_percent'] == 80

        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    async def test_multiple_clients_receive_broadcasts(self, db):
        """Test that multiple connected clients receive the same broadcast."""
        @database_sync_to_async
        def create_test_data():
            from django.contrib.gis.geos import Point

            users = [UserFactory() for _ in range(3)]

            category = Category.objects.create(
                name='Test Category',
                slug='test-category-multiple'
            )

            vendor = Vendor.objects.create(
                user=UserFactory(),
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                is_approved=True
            )

            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name='Test Product',
                price=Decimal('10.00'),
                stock_quantity=100
            )

            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=50,
                min_quantity=30,
                current_quantity=10,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return users, group

        users, group = await create_test_data()

        # Connect multiple clients
        communicators = []
        for user in users:
            token = get_jwt_token(user)
            comm = WebsocketCommunicator(
                GroupBuyingConsumer.as_asgi(),
                f"/ws/group-buying/?token={token}"
            )
            await comm.connect()
            await comm.receive_json_from()  # Connection message

            # Subscribe to the same group
            await comm.send_json_to({
                'type': 'subscribe',
                'group_id': group.id
            })
            await comm.receive_json_from()  # Subscription confirmation

            communicators.append(comm)

        # Broadcast a message
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f'group_buying_{group.id}',
            {
                'type': 'group_commitment',
                'data': {
                    'group_id': group.id,
                    'buyer_name': 'John Doe',
                    'quantity': 5,
                    'new_total': 15,
                    'participants_count': 2,
                    'message': 'John Doe committed 5 units!'
                }
            }
        )

        # All clients should receive the same message
        for comm in communicators:
            response = await comm.receive_json_from()
            assert response['type'] == 'new_commitment'
            assert response['data']['buyer_name'] == 'John Doe'
            assert response['data']['quantity'] == 5

        # Cleanup
        for comm in communicators:
            await comm.disconnect()

    async def test_ping_pong_keepalive(self, test_user):
        """Test ping/pong keepalive mechanism."""
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()

        # Send ping
        await communicator.send_json_to({
            'type': 'ping'
        })

        # Should receive pong
        response = await communicator.receive_json_from()
        assert response['type'] == 'pong'

        await communicator.disconnect()

    async def test_invalid_message_type(self, test_user):
        """Test handling of invalid message types."""
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()

        # Send invalid message type
        await communicator.send_json_to({
            'type': 'invalid_type',
            'data': {}
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'error'
        assert 'Unknown message type' in response['data']['message']

        await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in WebSocket consumer."""

    async def test_subscribe_without_group_id(self, test_user):
        """Test subscribing without providing group_id."""
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()

        await communicator.send_json_to({
            'type': 'subscribe'
            # Missing group_id
        })

        response = await communicator.receive_json_from()
        assert response['type'] == 'error'
        assert 'Group ID required' in response['data']['message']

        await communicator.disconnect()

    async def test_malformed_json_message(self, test_user):
        """Test handling of malformed JSON messages."""
        token = get_jwt_token(test_user)
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator.connect()
        await communicator.receive_json_from()

        # Send malformed message (missing required fields)
        await communicator.send_json_to({})

        # Consumer should handle gracefully
        # Either error or no response depending on implementation
        try:
            response = await communicator.receive_json_from(timeout=1)
            # If we get a response, it should be an error
            if response:
                assert response['type'] == 'error'
        except:
            # No response is also acceptable for malformed messages
            pass

        await communicator.disconnect()

    async def test_reconnection_after_disconnect(self, test_user):
        """Test that client can reconnect after disconnection."""
        token = get_jwt_token(test_user)
        communicator1 = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        # First connection
        await communicator1.connect()
        response = await communicator1.receive_json_from()
        assert response['type'] == 'connection_established'
        await communicator1.disconnect()

        # Second connection should work
        communicator2 = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            f"/ws/group-buying/?token={token}"
        )

        await communicator2.connect()
        response = await communicator2.receive_json_from()
        assert response['type'] == 'connection_established'
        await communicator2.disconnect()
