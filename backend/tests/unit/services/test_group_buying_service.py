"""
Unit tests for GroupBuyingService using TDD approach.
Tests business logic for group buying calculations, thresholds, and operations.
"""
from tests.conftest import UserFactory, AddressFactory
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from django.utils import timezone
from django.contrib.gis.geos import Point

from apps.buying_groups.services.group_buying_service import GroupBuyingService
from apps.buying_groups.models import BuyingGroup, GroupCommitment, GroupUpdate
from apps.core.services.base import ServiceResult


class TestGroupBuyingServiceCalculations:
    """Test business logic calculations for group buying."""

    def test_calculate_target_quantity_for_expensive_product(self, group_buying_service):
        """Test that expensive products (>£100) get target quantity of 10."""
        # Arrange
        product = Mock()
        product.price = Decimal('150.00')

        # Act
        target = group_buying_service._calculate_target_quantity(product)

        # Assert
        assert target == 10

    def test_calculate_target_quantity_for_medium_price_product(self, group_buying_service):
        """Test that medium priced products (£50-100) get target quantity of 20."""
        # Arrange
        product = Mock()
        product.price = Decimal('75.00')

        # Act
        target = group_buying_service._calculate_target_quantity(product)

        # Assert
        assert target == 20

    def test_calculate_target_quantity_for_low_price_product(self, group_buying_service):
        """Test that low priced products (<£20) get target quantity of 50."""
        # Arrange
        product = Mock()
        product.price = Decimal('15.00')

        # Act
        target = group_buying_service._calculate_target_quantity(product)

        # Assert
        assert target == 50

    def test_calculate_discount_percent_based_on_quantity(self, group_buying_service):
        """Test discount calculation based on target quantity."""
        # Arrange
        product = Mock()
        product.price = Decimal('50.00')

        # Test high quantity (50+) gets 15% base discount
        discount = group_buying_service._calculate_discount_percent(
            product, 50)
        assert discount == Decimal('15.00')

        # Test medium quantity (30-49) gets 12% base discount
        discount = group_buying_service._calculate_discount_percent(
            product, 35)
        assert discount == Decimal('12.00')

        # Test low quantity (<20) gets 8% base discount
        discount = group_buying_service._calculate_discount_percent(
            product, 15)
        assert discount == Decimal('8.00')

    def test_calculate_discount_increased_for_expensive_items(self, group_buying_service):
        """Test that expensive items get higher discounts."""
        # Arrange
        product = Mock()
        product.price = Decimal('150.00')  # Expensive item

        # Act
        discount = group_buying_service._calculate_discount_percent(
            product, 50)

        # Assert
        # 15% base (for 50 quantity) + 5% (for price > 100) = 20%
        assert discount == Decimal('20.00')

    @pytest.mark.skip(reason="calculate_commitment_amount method no longer exists in service")
    def test_calculate_commitment_amount_with_discount_and_vat(self, group_buying_service):
        """Test calculation of commitment amount including discount and VAT."""
        # Arrange
        group = Mock()
        group.product.price = Decimal('100.00')
        group.product.vat_rate = Decimal('0.20')
        group.discount_percent = Decimal('15.00')
        quantity = 5

        # Act
        amount = group_buying_service.calculate_commitment_amount(
            group, quantity)

        # Assert
        # Calculation: 100 * 5 * 0.85 = 425 (after discount)
        # VAT: 425 * 0.20 = 85
        # Total: 425 + 85 = 510
        expected = Decimal('510.00')
        assert amount == expected


class TestGroupBuyingServiceCreation:
    """Test group buying creation with business rules."""

    @pytest.mark.django_db
    def test_create_group_success(
        self,
        group_buying_service,
        test_product,
        mock_geocoding_response
    ):
        """Test successful group creation with auto-calculated values."""
        # Arrange
        test_product.stock_quantity = 100
        test_product.save()

        # Act
        result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA',
            duration_days=7
        )

        # Assert
        assert result.success is True
        assert result.data is not None

        group = result.data
        assert isinstance(group, BuyingGroup)
        assert group.product == test_product
        assert group.status == 'open'
        assert group.area_name == 'Westminster'

        # Check auto-calculated values
        assert group.target_quantity > 0
        assert group.discount_percent >= Decimal('5.00')
        assert group.discount_percent <= Decimal('50.00')
        assert group.min_quantity == int(
            group.target_quantity * Decimal('0.60'))

    @pytest.mark.django_db
    def test_create_group_fails_with_inactive_product(
        self,
        group_buying_service,
        test_product,
        mock_geocoding_response
    ):
        """Test that group creation fails for inactive products."""
        # Arrange
        test_product.is_active = False
        test_product.save()

        # Act
        result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'PRODUCT_INACTIVE'

    @pytest.mark.django_db
    def test_create_group_fails_with_insufficient_stock(
        self,
        group_buying_service,
        test_product,
        mock_geocoding_response
    ):
        """Test that group creation fails when product has low stock."""
        # Arrange
        test_product.stock_quantity = 5  # Below minimum of 10
        test_product.save()

        # Act
        result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA'
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'INSUFFICIENT_STOCK'

    @pytest.mark.django_db
    def test_create_group_validates_duration_limits(
        self,
        group_buying_service,
        test_product,
        mock_geocoding_response
    ):
        """Test that group duration must be within allowed limits."""
        # Test duration too long
        result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA',
            duration_days=31  # Exceeds 30 day maximum
        )
        assert result.success is False
        assert result.error_code == 'DURATION_TOO_LONG'

        # Test duration too short
        result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA',
            duration_days=0
        )
        assert result.success is False
        assert result.error_code == 'DURATION_TOO_SHORT'


class TestGroupBuyingCommitments:
    """Test commitment operations and business rules."""

    @pytest.mark.django_db
    def test_commit_to_group_success(
        self,
        group_buying_service,
        test_buying_group,
        test_user,
        test_address,
        mock_geocoding_response,
        mock_stripe_payment_intent
    ):
        """Test successful commitment to a buying group."""
        # Arrange
        test_buying_group.status = 'open'
        test_buying_group.save()

        mock_stripe_result = ServiceResult.ok({'intent_id': 'pi_test_123'})

        with patch('apps.integrations.services.stripe_service.StripeConnectService.create_payment_intent_for_group') as mock_stripe:
            mock_stripe.return_value = mock_stripe_result

            # Act
            result = group_buying_service.commit_to_group(
                group_id=test_buying_group.id,
                buyer=test_user,
                quantity=5,
                buyer_postcode='SW1A 1AA',
                delivery_address_id=test_address.id
            )

        # Assert
        assert result.success is True
        commitment = result.data['commitment']
        assert isinstance(commitment, GroupCommitment)
        assert commitment.buyer == test_user
        assert commitment.quantity == 5
        assert commitment.status == 'pending'

        # Verify group quantity was updated
        test_buying_group.refresh_from_db()
        assert test_buying_group.current_quantity == 5

    @pytest.mark.django_db
    def test_commit_to_group_prevents_duplicate(
        self,
        group_buying_service,
        test_buying_group,
        test_user,
        test_address,
        mock_geocoding_response
    ):
        """Test that users cannot commit to the same group twice."""
        # Arrange
        # Create existing commitment
        from tests.conftest import GroupCommitmentFactory
        GroupCommitmentFactory(
            group=test_buying_group,
            buyer=test_user,
            quantity=5,
            buyer_location=Point(-0.1276, 51.5074),
            buyer_postcode='SW1A 1AA',
            delivery_address=test_address,
            status='pending'
        )

        # Act
        result = group_buying_service.commit_to_group(
            group_id=test_buying_group.id,
            buyer=test_user,
            quantity=3,
            buyer_postcode='SW1A 1AA',
            delivery_address_id=test_address.id
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'ALREADY_COMMITTED'

    @pytest.mark.django_db
    def test_commit_to_group_validates_location(
        self,
        group_buying_service,
        test_buying_group,
        test_user,
        test_address
    ):
        """Test that commitment validates buyer is within group radius."""
        # Arrange
        # London
        test_buying_group.center_point = Point(-0.1276, 51.5074, srid=4326)
        test_buying_group.radius_km = 50  # 50km radius
        test_buying_group.save()

        # Mock geocoding to return location far outside radius (Sydney, Australia)
        mock_location = Mock()
        mock_location.success = True
        mock_location.data = {
            # Sydney, Australia - definitely outside 50km radius from London
            'point': Point(151.2093, -33.8688, srid=4326)
        }

        with patch('apps.integrations.services.geocoding_service.GeocodingService.geocode_postcode') as mock_geo:
            mock_geo.return_value = mock_location

            # Act
            result = group_buying_service.commit_to_group(
                group_id=test_buying_group.id,
                buyer=test_user,
                quantity=5,
                buyer_postcode='SYD 2000',
                delivery_address_id=test_address.id
            )

        # Assert
        assert result.success is False
        assert result.error_code == 'OUT_OF_RADIUS'

    @pytest.mark.django_db
    def test_commit_triggers_threshold_notification(
        self,
        group_buying_service,
        test_buying_group,
        test_user,
        test_address,
        mock_geocoding_response,
        mock_stripe_payment_intent
    ):
        """Test that reaching target quantity triggers notification."""
        # Arrange
        test_buying_group.current_quantity = 95
        test_buying_group.target_quantity = 100
        test_buying_group.product.stock_quantity = 200
        test_buying_group.product.save()
        test_buying_group.save()

        mock_stripe_result = ServiceResult.ok({'intent_id': 'pi_test_123'})

        with patch('apps.integrations.services.stripe_service.StripeConnectService.create_payment_intent_for_group') as mock_stripe:
            mock_stripe.return_value = mock_stripe_result

            # Act
            result = group_buying_service.commit_to_group(
                group_id=test_buying_group.id,
                buyer=test_user,
                quantity=5,  # This will reach the target
                buyer_postcode='SW1A 1AA',
                delivery_address_id=test_address.id
            )

        # Assert
        assert result.success is True

        # When target is reached, group is processed immediately and status becomes 'completed'
        test_buying_group.refresh_from_db()
        assert test_buying_group.status == 'completed'

        # Check that threshold event was created
        threshold_event = GroupUpdate.objects.filter(
            group=test_buying_group,
            event_type='threshold'
        ).first()
        assert threshold_event is not None


class TestGroupBuyingExpiration:
    """Test group expiration and processing logic."""

    @pytest.mark.django_db
    def test_process_expired_groups_success(
        self,
        group_buying_service,
        test_product
    ):
        """Test processing groups that reached minimum quantity."""
        # Arrange
        # Create expired group that met minimum
        expired_group = BuyingGroup.objects.create(
            product=test_product,
            center_point=Point(-0.1276, 51.5074),
            radius_km=5,
            area_name='Test Area',
            target_quantity=100,
            current_quantity=65,  # Above minimum (60)
            min_quantity=60,
            discount_percent=Decimal('15.00'),
            expires_at=timezone.now() - timedelta(hours=1),  # Expired
            status='open'
        )

        # Act
        stats = group_buying_service.process_expired_groups()

        # Assert
        assert stats['total_processed'] == 1
        assert stats['successful'] == 1
        assert stats['failed'] == 0

        # Verify group was marked as active
        expired_group.refresh_from_db()
        assert expired_group.status == 'active'

    @pytest.mark.django_db
    def test_process_expired_groups_failure(
        self,
        group_buying_service,
        test_product
    ):
        """Test processing groups that didn't reach minimum quantity."""
        # Arrange
        # Create expired group that didn't meet minimum
        expired_group = BuyingGroup.objects.create(
            product=test_product,
            center_point=Point(-0.1276, 51.5074),
            radius_km=5,
            area_name='Test Area',
            target_quantity=100,
            current_quantity=50,  # Below minimum (60)
            min_quantity=60,
            discount_percent=Decimal('15.00'),
            expires_at=timezone.now() - timedelta(hours=1),  # Expired
            status='open'
        )

        # Create a commitment to test payment cancellation
        from tests.conftest import GroupCommitmentFactory
        buyer = UserFactory()
        commitment = GroupCommitmentFactory(
            group=expired_group,
            buyer=buyer,
            quantity=50,
            buyer_location=Point(-0.1276, 51.5074),
            buyer_postcode='SW1A 1AA',
            stripe_payment_intent_id='pi_test_cancel',
            status='pending'
        )

        with patch('apps.integrations.services.stripe_service.StripeConnectService.cancel_payment_intent') as mock_cancel:
            mock_cancel.return_value = ServiceResult.ok({'cancelled': True})

            # Act
            stats = group_buying_service.process_expired_groups()

        # Assert
        assert stats['total_processed'] == 1
        assert stats['successful'] == 0
        assert stats['failed'] == 1

        # Verify group was marked as failed
        expired_group.refresh_from_db()
        assert expired_group.status == 'failed'

        # Verify commitment was cancelled
        commitment.refresh_from_db()
        assert commitment.status == 'cancelled'

        # Verify payment intent was cancelled
        mock_cancel.assert_called_once_with('pi_test_cancel')


class TestGroupBuyingCancellation:
    """Test commitment cancellation logic."""

    @pytest.mark.django_db
    def test_cancel_commitment_success(
        self,
        group_buying_service,
        test_buying_group,
        test_user
    ):
        """Test successful commitment cancellation."""
        # Arrange
        test_buying_group.current_quantity = 50
        test_buying_group.save()

        from tests.conftest import GroupCommitmentFactory
        commitment = GroupCommitmentFactory(
            group=test_buying_group,
            buyer=test_user,
            quantity=10,
            buyer_location=Point(-0.1276, 51.5074),
            buyer_postcode='SW1A 1AA',
            stripe_payment_intent_id='pi_test_cancel',
            status='pending'
        )

        with patch('apps.integrations.services.stripe_service.StripeConnectService.cancel_payment_intent') as mock_cancel:
            mock_cancel.return_value = ServiceResult.ok({'cancelled': True})

            # Act
            result = group_buying_service.cancel_commitment(
                commitment_id=commitment.id,
                buyer=test_user
            )

        # Assert
        assert result.success is True

        # Verify commitment was cancelled
        commitment.refresh_from_db()
        assert commitment.status == 'cancelled'

        # Verify group quantity was updated
        test_buying_group.refresh_from_db()
        assert test_buying_group.current_quantity == 40  # 50 - 10

        # Verify payment was cancelled
        mock_cancel.assert_called_once_with('pi_test_cancel')

    @pytest.mark.django_db
    def test_cancel_commitment_prevents_after_processing(
        self,
        group_buying_service,
        test_buying_group,
        test_user
    ):
        """Test that commitments cannot be cancelled after group processing."""
        # Arrange
        test_buying_group.status = 'completed'  # Already processed
        test_buying_group.save()

        from tests.conftest import GroupCommitmentFactory
        commitment = GroupCommitmentFactory(
            group=test_buying_group,
            buyer=test_user,
            quantity=10,
            buyer_location=Point(-0.1276, 51.5074),
            buyer_postcode='SW1A 1AA',
            status='pending'
        )

        # Act
        result = group_buying_service.cancel_commitment(
            commitment_id=commitment.id,
            buyer=test_user
        )

        # Assert
        assert result.success is False
        assert result.error_code == 'CANNOT_LEAVE'


class TestGroupBuyingIntegration:
    """Integration tests for group buying with other services."""

    @pytest.mark.django_db
    def test_full_group_buying_lifecycle(
        self,
        group_buying_service,
        test_product,
        test_user,
        mock_geocoding_response
    ):
        """Test complete group buying lifecycle from creation to completion."""
        # 1. Create group
        test_product.price = Decimal('50.00')
        test_product.stock_quantity = 200
        test_product.save()

        create_result = group_buying_service.create_group_for_area(
            product_id=test_product.id,
            postcode='SW1A 1AA',
            target_quantity=20,
            discount_percent=Decimal('10.00')
        )

        assert create_result.success is True
        group = create_result.data

        # 2. Add commitments
        from tests.conftest import AddressFactory
        buyers = [UserFactory() for _ in range(4)]
        addresses = [AddressFactory(user=buyer) for buyer in buyers]

        with patch('apps.integrations.services.stripe_service.StripeConnectService.create_payment_intent_for_group') as mock_stripe:
            mock_stripe.return_value = ServiceResult.ok(
                {'intent_id': 'pi_test'})

            for buyer, address in zip(buyers, addresses):
                commit_result = group_buying_service.commit_to_group(
                    group_id=group.id,
                    buyer=buyer,
                    quantity=5,  # 4 buyers * 5 = 20 (reaches target)
                    buyer_postcode='SW1A 1AA',
                    delivery_address_id=address.id
                )
                assert commit_result.success is True

        # 3. When target is reached, group is processed immediately and status becomes 'completed'
        group.refresh_from_db()
        assert group.current_quantity == 20
        assert group.status == 'completed'

        # 4. Process the group
        with patch.object(group_buying_service, '_process_successful_group') as mock_process:
            # Simulate expiration
            group.expires_at = timezone.now() - timedelta(hours=1)
            group.status = 'open'  # Reset for processing
            group.save()

            stats = group_buying_service.process_expired_groups()

            assert stats['successful'] == 1
            mock_process.assert_called_once()
