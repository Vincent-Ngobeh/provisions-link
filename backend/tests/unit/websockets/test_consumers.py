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

from apps.buying_groups.consumers import GroupBuyingConsumer
from apps.buying_groups.models import BuyingGroup, GroupCommitment
from tests.conftest import BuyingGroupFactory, UserFactory, ProductFactory

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestGroupBuyingConsumerConnection:
    """Test WebSocket connection handling."""

    async def test_anonymous_user_can_connect(self):
        """Test that anonymous users can connect to view updates."""
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/group-buying/"
        )

        connected, _ = await communicator.connect()
        assert connected is True

        # Should receive connection confirmation
        response = await communicator.receive_json_from()
        assert response['type'] == 'connection_established'
        assert response['data']['authenticated'] is False

        await communicator.disconnect()

    async def test_authenticated_user_can_connect(self, test_user):
        """Test that authenticated users can connect."""
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/group-buying/"
        )

        # Set user in scope
        communicator.scope['user'] = test_user

        connected, _ = await communicator.connect()
        assert connected is True

        # Should receive connection confirmation
        response = await communicator.receive_json_from()
        assert response['type'] == 'connection_established'
        assert response['data']['authenticated'] is True

        await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestGroupSubscription:
    """Test group subscription functionality."""

    @pytest.mark.django_db(transaction=True)
    async def test_subscribe_to_valid_group(self, db, test_user):
        """Test subscribing to a valid group."""
        from apps.buying_groups.models import BuyingGroup
        from apps.products.models import Product, Category
        from apps.vendors.models import Vendor
        from apps.core.models import User
        from django.contrib.gis.geos import Point
        from decimal import Decimal
        from django.utils import timezone
        from datetime import timedelta

        # Wrap all database operations in sync_to_async
        @database_sync_to_async
        def create_test_data():
            # Create vendor with user
            vendor_user = User.objects.create_user(
                email='vendor@test.com',
                username='vendor_test'
            )
            vendor = Vendor.objects.create(
                user=vendor_user,
                business_name='Test Vendor',
                location=Point(-0.1276, 51.5074),
                postcode='SW1A 1AA',
                is_approved=True,
                commission_rate=Decimal('0.10')
            )

            # Create category (REQUIRED for Product)
            category = Category.objects.create(
                name='Food & Beverages',
                slug='food-beverages',
                display_order=1
            )

            # Create product with category
            product = Product.objects.create(
                vendor=vendor,
                category=category,  # Required field
                name='Test Product',
                slug='test-product',  # Add slug if required
                price=Decimal('10.00'),
                stock_quantity=100,
                is_active=True,
                vat_rate=Decimal('0.20'),
                unit='unit',  # Add unit if required
                description='Test product description'
            )

            # Create buying group
            group = BuyingGroup.objects.create(
                product=product,
                center_point=Point(-0.1276, 51.5074),
                radius_km=5,
                area_name='Test Area',
                target_quantity=100,
                current_quantity=0,
                min_quantity=60,
                discount_percent=Decimal('15.00'),
                expires_at=timezone.now() + timedelta(days=7),
                status='open'
            )

            return group

        # Create all test data synchronously
        group = await create_test_data()

        # Now test the WebSocket
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/group-buying/"
        )
        communicator.scope['user'] = test_user

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
        communicator = WebsocketCommunicator(
            GroupBuyingConsumer.as_asgi(),
            "/ws/group-buying/"
        )
        communicator.scope['user'] = test_user

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
