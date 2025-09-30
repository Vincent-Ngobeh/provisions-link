"""
Unit tests for OrderService.
Tests order creation, processing, status transitions, and business rules.
"""
from tests.conftest import UserFactory, VendorFactory, ProductFactory, GroupCommitmentFactory, OrderFactory
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.utils import timezone
from django.contrib.gis.geos import Point

from apps.orders.services.order_service import OrderService
from apps.orders.models import Order, OrderItem
from apps.products.models import Product
from apps.core.services.base import ServiceResult


class TestOrderCalculations:
    """Test order pricing and fee calculations."""

    def test_calculate_delivery_fee_free_for_high_value_orders(self, order_service):
        """Test that orders over £150 get free delivery."""
        # Arrange
        subtotal = Decimal('200.00')
        vendor = Mock()
        address = Mock()

        # Act
        fee = order_service._calculate_delivery_fee(subtotal, vendor, address)

        # Assert
        assert fee == Decimal('0.00')

    def test_calculate_delivery_fee_standard_for_low_value_orders(self, order_service):
        """Test that orders under £150 pay standard delivery fee."""
        # Arrange
        subtotal = Decimal('100.00')
        vendor = Mock()
        vendor.location = None
        address = Mock()
        address.location = None

        # Act
        fee = order_service._calculate_delivery_fee(subtotal, vendor, address)

        # Assert
        assert fee == OrderService.DEFAULT_DELIVERY_FEE

    def test_calculate_delivery_fee_based_on_distance(self, order_service):
        """Test distance-based delivery fee calculation."""
        # Arrange
        subtotal = Decimal('100.00')
        vendor = Mock()
        vendor.location = Point(-0.1276, 51.5074)  # London
        address = Mock()
        address.location = Point(-0.1376, 51.5174)  # ~1km away

        with patch('apps.integrations.services.geocoding_service.GeocodingService.calculate_distance') as mock_distance:
            mock_distance.return_value = Decimal('5.5')  # 5.5km distance

            # Act
            fee = order_service._calculate_delivery_fee(
                subtotal, vendor, address)

            # Assert
            # £5 base + £2.50 for 2.5km over 3km = £7.50
            expected_fee = Decimal('5.00') + Decimal('2.5')
            assert fee == expected_fee

    def test_apply_group_discount_when_active(self, order_service, test_buying_group):
        """Test that group discount is applied when group is active."""
        # Arrange
        test_buying_group.status = 'active'
        test_buying_group.discount_percent = Decimal('15.00')
        test_buying_group.save()

        original_price = Decimal('100.00')

        # Act
        with patch('apps.buying_groups.models.BuyingGroup.objects.get') as mock_get:
            mock_get.return_value = test_buying_group

            result = order_service._apply_group_discount(
                group_id=test_buying_group.id,
                product_id=test_buying_group.product.id,
                original_price=original_price
            )

        # Assert
        assert result.success is True
        assert result.data['discount_amount'] == Decimal('15.00')  # 15% of 100
        assert result.data['discount_percent'] == Decimal('15.00')

    @pytest.mark.django_db
    def test_apply_no_discount_when_group_not_active(self, order_service):
        """Test that no discount is applied when group doesn't exist or isn't active."""
        # Act
        result = order_service._apply_group_discount(
            group_id=999,  # Non-existent
            product_id=1,
            original_price=Decimal('100.00')
        )

        # Assert
        assert result.success is True
        assert result.data['discount_amount'] == Decimal('0.00')
        assert result.data['discount_percent'] == Decimal('0.00')


class TestOrderCreation:
    """Test order creation with validation."""

    @pytest.mark.django_db
    def test_create_order_success(
        self,
        order_service,
        test_user,
        approved_vendor,
        test_address,
        test_product
    ):
        """Test successful order creation with multiple items."""
        # Arrange
        test_product.vendor = approved_vendor
        test_product.stock_quantity = 100
        test_product.price = Decimal('25.00')
        test_product.save()

        product2 = ProductFactory(
            vendor=approved_vendor,
            stock_quantity=50,
            price=Decimal('30.00')
        )

        items = [
            {'product_id': test_product.id, 'quantity': 2},
            {'product_id': product2.id, 'quantity': 3}
        ]

        # Act
        result = order_service.create_order(
            buyer=test_user,
            vendor_id=approved_vendor.id,
            delivery_address_id=test_address.id,
            items=items,
            delivery_notes='Please ring doorbell'
        )

        # Assert
        assert result.success is True
        order = result.data
        assert isinstance(order, Order)
        assert order.buyer == test_user
        assert order.vendor == approved_vendor
        assert order.status == 'pending'

        # Check calculations
        # Subtotal: (25*2) + (30*3) = 140
        # VAT: 140 * 0.20 = 28
        # Delivery: 5 (under £150 threshold)
        # Total: 140 + 28 + 5 = 173
        assert order.subtotal == Decimal('140.00')
        assert order.vat_amount == Decimal('28.00')
        assert order.delivery_fee == Decimal('5.00')
        assert order.total == Decimal('173.00')

        # Check commission calculation (10% of subtotal)
        assert order.marketplace_fee == Decimal('14.00')
        assert order.vendor_payout == Decimal('159.00')  # Total - commission

        # Check stock was reserved
        test_product.refresh_from_db()
        product2.refresh_from_db()
        assert test_product.stock_quantity == 98  # 100 - 2
        assert product2.stock_quantity == 47  # 50 - 3

    @pytest.mark.django_db
    def test_create_order_validates_minimum_value(
        self,
        order_service,
        test_user,
        approved_vendor,
        test_address,
        test_product
    ):
        """Test that order must meet vendor's minimum value."""
        # Arrange
        approved_vendor.min_order_value = Decimal('100.00')
        approved_vendor.save()

        test_product.vendor = approved_vendor
        test_product.price = Decimal('10.00')
        test_product.save()

        items = [{'product_id': test_product.id, 'quantity': 5}]  # Only £50

        # Act
        result = order_service.create_order(
            buyer=test_user,
            vendor_id=approved_vendor.id,
            delivery_address_id=test_address.id,
            items=items
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'BELOW_MINIMUM'
        assert f"at least £{approved_vendor.min_order_value}" in result.error

    @pytest.mark.django_db
    def test_create_order_validates_stock_availability(
        self,
        order_service,
        test_user,
        approved_vendor,
        test_address,
        test_product
    ):
        """Test that order creation fails when insufficient stock."""
        # Arrange
        test_product.vendor = approved_vendor
        test_product.stock_quantity = 5
        test_product.save()

        # More than available
        items = [{'product_id': test_product.id, 'quantity': 10}]

        # Act
        result = order_service.create_order(
            buyer=test_user,
            vendor_id=approved_vendor.id,
            delivery_address_id=test_address.id,
            items=items
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INSUFFICIENT_STOCK'
        assert 'Insufficient stock' in result.error

    @pytest.mark.django_db
    def test_create_order_validates_product_belongs_to_vendor(
        self,
        order_service,
        test_user,
        approved_vendor,
        test_address,
        test_product
    ):
        """Test that all products in order must belong to the same vendor."""
        # Arrange
        other_vendor = VendorFactory()
        test_product.vendor = other_vendor  # Different vendor
        test_product.save()

        items = [{'product_id': test_product.id, 'quantity': 1}]

        # Act
        result = order_service.create_order(
            buyer=test_user,
            vendor_id=approved_vendor.id,
            delivery_address_id=test_address.id,
            items=items
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'PRODUCT_NOT_FOUND'

    @pytest.mark.django_db
    def test_create_order_with_group_discount(
        self,
        order_service,
        test_user,
        approved_vendor,
        test_address,
        test_product,
        test_buying_group
    ):
        """Test order creation with group buying discount."""
        # Arrange
        test_product.vendor = approved_vendor
        test_product.price = Decimal('100.00')
        test_product.save()

        test_buying_group.product = test_product
        test_buying_group.status = 'active'
        test_buying_group.discount_percent = Decimal('20.00')
        test_buying_group.save()

        items = [{'product_id': test_product.id, 'quantity': 1}]

        # Act
        result = order_service.create_order(
            buyer=test_user,
            vendor_id=approved_vendor.id,
            delivery_address_id=test_address.id,
            items=items,
            group_id=test_buying_group.id
        )

        # Assert
        assert result.success is True
        order = result.data

        # Check discount was applied
        # Original: £100
        # Discount: 20% = £20
        # Subtotal: £80
        # VAT: £16
        # Total: £96 + delivery
        assert order.subtotal == Decimal('80.00')

        # Check order item has discount
        order_item = order.items.first()
        assert order_item.discount_amount == Decimal('20.00')


class TestOrderFromGroupBuying:
    """Test creating orders from group buying commitments."""

    @pytest.mark.django_db
    def test_create_order_from_group_success(
        self,
        order_service,
        test_buying_group,
        test_user,
        test_address
    ):
        """Test successful order creation from group commitment."""
        # Arrange
        test_buying_group.status = 'active'
        test_buying_group.discount_percent = Decimal('15.00')
        test_buying_group.save()

        test_address.user = test_user
        test_address.is_default = True
        test_address.save()

        commitment = GroupCommitmentFactory(
            group=test_buying_group,
            buyer=test_user,
            quantity=5,
            status='pending',
            stripe_payment_intent_id='pi_test_123'
        )

        with patch('apps.integrations.services.stripe_service.StripeConnectService.capture_group_payment') as mock_capture:
            mock_capture.return_value = ServiceResult.ok({'captured': True})

            # Act
            result = order_service.create_order_from_group(
                group_id=test_buying_group.id,
                commitment_id=commitment.id
            )

        # Assert
        assert result.success is True
        order = result.data
        assert isinstance(order, Order)
        assert order.buyer == test_user
        assert order.group == test_buying_group
        assert order.status == 'paid'  # Should be paid after capture
        assert order.paid_at is not None

        # Verify discount was applied
        order_item = order.items.first()
        assert order_item.quantity == 5
        assert order_item.discount_amount > Decimal('0.00')

        # Verify commitment was confirmed
        commitment.refresh_from_db()
        assert commitment.status == 'confirmed'

        # Verify payment was captured
        mock_capture.assert_called_once_with('pi_test_123')


class TestOrderStatusTransitions:
    """Test order status update logic and transitions."""

    @pytest.mark.django_db
    def test_update_status_valid_transition(
        self,
        order_service,
        test_order,
        test_user
    ):
        """Test valid status transition from pending to paid."""
        # Arrange
        test_order.status = 'pending'
        test_order.buyer = test_user
        test_order.save()

        # Act
        result = order_service.update_order_status(
            order_id=test_order.id,
            new_status='paid',
            user=test_user,
            notes='Payment confirmed'
        )

        # Assert
        assert result.success is True
        assert result.data['old_status'] == 'pending'
        assert result.data['new_status'] == 'paid'

        test_order.refresh_from_db()
        assert test_order.status == 'paid'
        assert test_order.paid_at is not None

    @pytest.mark.django_db
    def test_update_status_invalid_transition(
        self,
        order_service,
        test_order,
        test_user
    ):
        """Test that invalid status transitions are rejected."""
        # Arrange
        test_order.status = 'delivered'
        test_order.buyer = test_user
        test_order.save()

        # Make user staff so they pass permission check
        test_user.is_staff = True
        test_user.save()

        # Act
        result = order_service.update_order_status(
            order_id=test_order.id,
            new_status='pending',  # Can't go back to pending from delivered
            user=test_user
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INVALID_TRANSITION'

    @pytest.mark.django_db
    def test_update_status_permission_check(
        self,
        order_service,
        test_order
    ):
        """Test that only authorized users can update order status."""
        # Arrange
        other_user = UserFactory()
        test_order.status = 'pending'
        test_order.save()

        # Act
        result = order_service.update_order_status(
            order_id=test_order.id,
            new_status='paid',
            user=other_user  # Not the buyer or vendor
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'PERMISSION_DENIED'

    @pytest.mark.django_db
    def test_cancel_order_returns_stock(
        self,
        order_service,
        test_order,
        test_product
    ):
        """Test that cancelling an order returns stock to inventory."""
        # Arrange
        test_order.status = 'pending'
        test_order.save()

        initial_stock = 50
        test_product.stock_quantity = initial_stock
        test_product.save()

        OrderItem.objects.create(
            order=test_order,
            product=test_product,
            quantity=10,
            unit_price=test_product.price,
            total_price=test_product.price * 10
        )

        with patch('apps.integrations.services.stripe_service.StripeConnectService.cancel_payment_intent'):
            # Act
            order_service._handle_order_cancellation(test_order)

        # Assert
        test_product.refresh_from_db()
        assert test_product.stock_quantity == initial_stock + 10  # Stock returned


class TestOrderPaymentProcessing:
    """Test order payment processing."""

    @pytest.mark.django_db
    def test_process_payment_success(
        self,
        order_service,
        test_order,
        approved_vendor
    ):
        """Test successful payment processing."""
        # Arrange
        test_order.status = 'pending'
        test_order.vendor = approved_vendor
        test_order.save()

        mock_payment_result = ServiceResult.ok({
            'payment_intent_id': 'pi_test_123',
            'client_secret': 'secret_123',
            'amount': 10000,
            'commission': 1000,
            'vendor_amount': 9000
        })

        with patch('apps.integrations.services.stripe_service.StripeConnectService.process_marketplace_order') as mock_stripe:
            mock_stripe.return_value = mock_payment_result

            # Act
            result = order_service.process_payment(
                order_id=test_order.id,
                payment_method_id='pm_test_123'
            )

        # Assert
        assert result.success is True
        assert result.data['payment_status'] == 'succeeded'

        test_order.refresh_from_db()
        assert test_order.status == 'paid'
        assert test_order.paid_at is not None

    @pytest.mark.django_db
    def test_process_payment_requires_pending_status(
        self,
        order_service,
        test_order
    ):
        """Test that payment can only be processed for pending orders."""
        # Arrange
        test_order.status = 'delivered'  # Already completed
        test_order.save()

        # Act
        result = order_service.process_payment(
            order_id=test_order.id,
            payment_method_id='pm_test_123'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INVALID_STATUS'


class TestOrderAnalytics:
    """Test order analytics and reporting."""

    @pytest.mark.django_db
    def test_get_order_analytics_for_vendor(
        self,
        order_service,
        approved_vendor
    ):
        """Test generating analytics for a specific vendor."""
        # Arrange
        # Create some test orders
        for i in range(5):
            order = OrderFactory(
                vendor=approved_vendor,
                status='delivered' if i < 3 else 'pending',
                total=Decimal('100.00'),
                marketplace_fee=Decimal('10.00')
            )
            # Create order items
            OrderItem.objects.create(
                order=order,
                product=ProductFactory(vendor=approved_vendor),
                quantity=2,
                unit_price=Decimal('50.00'),
                total_price=Decimal('100.00')
            )

        # Act
        result = order_service.get_order_analytics(
            vendor_id=approved_vendor.id,
            date_from=timezone.now() - timedelta(days=30),
            date_to=timezone.now()
        )

        # Assert
        assert result.success is True
        analytics = result.data

        # Check summary stats
        assert analytics['summary']['total_orders'] == 5
        assert analytics['summary']['total_revenue'] == 500.0  # 5 * 100
        assert analytics['summary']['total_commission'] == 50.0  # 5 * 10
        assert analytics['summary']['average_order_value'] == 100.0

        # Check status breakdown
        assert analytics['status_breakdown']['delivered'] == 3
        assert analytics['status_breakdown']['pending'] == 2

    @pytest.mark.django_db
    def test_get_order_analytics_date_filtering(
        self,
        order_service,
        approved_vendor
    ):
        """Test that analytics correctly filter by date range."""
        # Arrange
        # Create old order (outside range)
        old_order = OrderFactory(
            vendor=approved_vendor,
            status='delivered',
            total=Decimal('100.00'),
            created_at=timezone.now() - timedelta(days=60)
        )

        # Create recent order (inside range)
        recent_order = OrderFactory(
            vendor=approved_vendor,
            status='delivered',
            total=Decimal('200.00')
        )

        # Act
        result = order_service.get_order_analytics(
            vendor_id=approved_vendor.id,
            date_from=timezone.now() - timedelta(days=30),
            date_to=timezone.now()
        )

        # Assert
        assert result.success is True
        analytics = result.data

        # Should only include recent order
        assert analytics['summary']['total_orders'] == 1
        assert analytics['summary']['total_revenue'] == 200.0
