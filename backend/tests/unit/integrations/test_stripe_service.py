"""
Unit tests for StripeConnectService.
Tests Stripe Connect integration for marketplace payments and vendor onboarding.
"""
from tests.conftest import VendorFactory
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import stripe

from django.conf import settings

from apps.integrations.services.stripe_service import StripeConnectService
from apps.vendors.models import Vendor
from apps.orders.models import Order
from apps.core.services.base import ServiceResult


class TestVendorAccountCreation:
    """Test Stripe Connect account creation for vendors."""

    @pytest.mark.django_db
    def test_create_vendor_account_success(self, stripe_service, test_vendor):
        """Test successful Stripe Connect account creation."""
        # Arrange
        test_vendor.stripe_account_id = None
        test_vendor.save()

        mock_account = MagicMock()
        mock_account.id = 'acct_test123456'

        mock_link = MagicMock()
        mock_link.url = 'https://connect.stripe.com/onboard/test123'
        mock_link.expires_at = 1234567890

        # Patch stripe.api_key to look like a live key to bypass test mode
        with patch.object(stripe, 'api_key', 'sk_live_mockedkey'):
            with patch('stripe.Account.create') as mock_create:
                mock_create.return_value = mock_account

                with patch.object(stripe_service, 'generate_onboarding_link') as mock_onboard:
                    mock_onboard.return_value = ServiceResult.ok({
                        'url': mock_link.url
                    })

                    # Act
                    result = stripe_service.create_vendor_account(test_vendor)

        # Assert
        assert result.success is True
        assert result.data['account_id'] == 'acct_test123456'
        assert result.data['onboarding_url'] == mock_link.url

        test_vendor.refresh_from_db()
        assert test_vendor.stripe_account_id == 'acct_test123456'

        # Verify account creation parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['type'] == 'express'
        assert call_args['country'] == 'GB'
        assert call_args['email'] == test_vendor.user.email
        assert call_args['business_profile']['name'] == test_vendor.business_name

    @pytest.mark.django_db
    def test_create_vendor_account_already_exists(self, stripe_service, test_vendor):
        """Test that duplicate account creation is prevented."""
        # Arrange
        test_vendor.stripe_account_id = 'acct_existing'
        test_vendor.save()

        # Act
        result = stripe_service.create_vendor_account(test_vendor)

        # Assert
        assert result.success is False
        assert result.error_code == 'ACCOUNT_EXISTS'

    @pytest.mark.django_db
    def test_create_vendor_account_handles_stripe_error(self, stripe_service, test_vendor):
        """Test handling of Stripe API errors during account creation."""
        # Arrange
        test_vendor.stripe_account_id = None
        test_vendor.save()

        # Patch stripe.api_key to look like a live key to bypass test mode
        with patch.object(stripe, 'api_key', 'sk_live_mockedkey'):
            with patch('stripe.Account.create') as mock_create:
                mock_create.side_effect = stripe.error.StripeError('API Error')

                # Act
                result = stripe_service.create_vendor_account(test_vendor)

        # Assert
        assert result.success is False
        assert result.error_code == 'STRIPE_ERROR'
        assert 'API Error' in result.error


class TestVendorOnboarding:
    """Test vendor onboarding link generation."""

    @pytest.mark.django_db
    def test_generate_onboarding_link_success(self, stripe_service, test_vendor):
        """Test successful onboarding link generation."""
        # Arrange
        # Use account ID that doesn't look like a mock (no underscores after acct_)
        test_vendor.stripe_account_id = 'acct_1234567890ABC'
        test_vendor.save()

        mock_account = MagicMock()
        mock_account.id = test_vendor.stripe_account_id

        mock_link = MagicMock()
        mock_link.url = 'https://connect.stripe.com/onboard/test'
        mock_link.expires_at = int(datetime.now().timestamp()) + 300

        # Patch stripe.api_key to look like a live key
        with patch.object(stripe, 'api_key', 'sk_live_mockedkey'):
            with patch('stripe.Account.retrieve') as mock_retrieve:
                mock_retrieve.return_value = mock_account

                with patch('stripe.AccountLink.create') as mock_create:
                    mock_create.return_value = mock_link

                    # Act
                    result = stripe_service.generate_onboarding_link(
                        test_vendor)

        # Assert
        assert result.success is True
        assert result.data['url'] == mock_link.url
        assert 'expires_at' in result.data

        # Verify link creation parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['account'] == 'acct_1234567890ABC'
        assert call_args['type'] == 'account_onboarding'

    @pytest.mark.django_db
    def test_generate_onboarding_link_no_account(self, stripe_service, test_vendor):
        """Test that onboarding link creation fails when account creation fails."""
        # Arrange
        test_vendor.stripe_account_id = None
        test_vendor.save()

        # Patch stripe.api_key to look like a live key
        with patch.object(stripe, 'api_key', 'sk_live_mockedkey'):
            # Mock account creation to fail
            with patch('stripe.Account.create') as mock_create:
                mock_create.side_effect = stripe.error.StripeError(
                    'Account creation failed')

                # Act
                result = stripe_service.generate_onboarding_link(test_vendor)

        # Assert
        assert result.success is False
        assert result.error_code == 'STRIPE_ERROR'


class TestAccountStatus:
    """Test checking vendor Stripe account status."""

    @pytest.mark.django_db
    def test_check_account_status_active(self, stripe_service, test_vendor):
        """Test checking status of active account."""
        # Arrange
        test_vendor.stripe_account_id = 'acct_test123'
        test_vendor.stripe_onboarding_complete = False
        test_vendor.save()

        mock_account = MagicMock()
        mock_account.charges_enabled = True
        mock_account.payouts_enabled = True
        mock_account.requirements.currently_due = []

        with patch('stripe.Account.retrieve') as mock_retrieve:
            mock_retrieve.return_value = mock_account

            # Act
            result = stripe_service.check_account_status(test_vendor)

        # Assert
        assert result.success is True
        assert result.data['status'] == 'active'
        assert result.data['charges_enabled'] is True
        assert result.data['payouts_enabled'] is True

        test_vendor.refresh_from_db()
        assert test_vendor.stripe_onboarding_complete is True

    @pytest.mark.django_db
    def test_check_account_status_pending(self, stripe_service, test_vendor):
        """Test checking status of pending account."""
        # Arrange
        test_vendor.stripe_account_id = 'acct_test123'
        test_vendor.save()

        mock_account = MagicMock()
        mock_account.charges_enabled = False
        mock_account.payouts_enabled = False
        mock_account.requirements.currently_due = ['business_profile.url']

        with patch('stripe.Account.retrieve') as mock_retrieve:
            mock_retrieve.return_value = mock_account

            # Act
            result = stripe_service.check_account_status(test_vendor)

        # Assert
        assert result.success is True
        assert result.data['status'] == 'pending'
        assert result.data['charges_enabled'] is False
        assert result.data['requirements'] == ['business_profile.url']


class TestMarketplaceOrderProcessing:
    """Test payment processing for marketplace orders."""

    @pytest.mark.django_db
    def test_process_marketplace_order_success(self, stripe_service, test_order, approved_vendor):
        """Test successful order payment processing with vendor split."""
        # Arrange
        test_order.vendor = approved_vendor
        test_order.total = Decimal('100.00')
        test_order.status = 'pending'
        test_order.save()

        approved_vendor.stripe_account_id = 'acct_vendor123'
        approved_vendor.stripe_onboarding_complete = True
        approved_vendor.commission_rate = Decimal('0.10')  # 10%
        approved_vendor.save()

        mock_intent = MagicMock()
        mock_intent.id = 'pi_test123'
        mock_intent.client_secret = 'pi_test123_secret'

        with patch('stripe.PaymentIntent.create') as mock_create:
            mock_create.return_value = mock_intent

            # Act
            result = stripe_service.process_marketplace_order(test_order)

        # Assert
        assert result.success is True
        assert result.data['payment_intent_id'] == 'pi_test123'
        assert result.data['client_secret'] == 'pi_test123_secret'
        assert result.data['amount'] == 10000  # £100 in pence
        assert result.data['commission'] == 1000  # £10 commission
        assert result.data['vendor_amount'] == 9000  # £90 to vendor

        test_order.refresh_from_db()
        assert test_order.stripe_payment_intent_id == 'pi_test123'
        assert test_order.marketplace_fee == Decimal('10.00')
        assert test_order.vendor_payout == Decimal('90.00')

        # Verify payment intent parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['amount'] == 10000
        assert call_args['currency'] == 'gbp'
        assert call_args['application_fee_amount'] == 1000
        assert call_args['transfer_data']['destination'] == 'acct_vendor123'

    @pytest.mark.django_db
    def test_process_marketplace_order_vendor_not_ready(self, stripe_service, test_order, test_vendor):
        """Test that payment fails if vendor not fully onboarded."""
        # Arrange
        test_order.vendor = test_vendor
        test_order.status = 'pending'
        test_order.save()

        test_vendor.stripe_onboarding_complete = False
        test_vendor.save()

        # Act
        result = stripe_service.process_marketplace_order(test_order)

        # Assert
        assert result.success is False
        assert result.error_code == 'VENDOR_NOT_READY'


class TestGroupBuyingPayments:
    """Test payment handling for group buying."""

    def test_create_payment_intent_for_group(self, stripe_service):
        """Test creating pre-authorized payment for group buying."""
        # Arrange
        amount = Decimal('50.00')
        group_id = 123
        buyer_id = 456

        mock_intent = MagicMock()
        mock_intent.id = 'pi_group123'
        mock_intent.client_secret = 'pi_group123_secret'

        with patch('stripe.PaymentIntent.create') as mock_create:
            mock_create.return_value = mock_intent

            # Act
            result = stripe_service.create_payment_intent_for_group(
                amount=amount,
                group_id=group_id,
                buyer_id=buyer_id
            )

        # Assert
        assert result.success is True
        assert result.data['intent_id'] == 'pi_group123'
        assert result.data['client_secret'] == 'pi_group123_secret'
        assert result.data['amount'] == 5000  # £50 in pence

        # Verify payment intent is set to manual capture
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['amount'] == 5000
        assert call_args['capture_method'] == 'manual'
        assert call_args['metadata']['type'] == 'group_buying'
        assert call_args['metadata']['group_id'] == '123'

    def test_capture_group_payment_success(self, stripe_service):
        """Test capturing pre-authorized payment."""
        # Arrange
        payment_intent_id = 'pi_group123'

        mock_intent = MagicMock()
        mock_intent.amount = 5000
        mock_intent.status = 'succeeded'

        with patch('stripe.PaymentIntent.capture') as mock_capture:
            mock_capture.return_value = mock_intent

            # Act
            result = stripe_service.capture_group_payment(payment_intent_id)

        # Assert
        assert result.success is True
        assert result.data['captured'] is True
        assert result.data['amount'] == 5000
        assert result.data['status'] == 'succeeded'

        mock_capture.assert_called_once_with(payment_intent_id)

    def test_capture_group_payment_already_captured(self, stripe_service):
        """Test handling of already captured payment."""
        # Arrange
        payment_intent_id = 'pi_group123'

        with patch('stripe.PaymentIntent.capture') as mock_capture:
            mock_capture.side_effect = stripe.error.InvalidRequestError(
                'Payment intent has already been captured',
                None
            )

            # Act
            result = stripe_service.capture_group_payment(payment_intent_id)

        # Assert
        assert result.success is True
        assert result.data['captured'] is True
        assert result.data['message'] == 'Already captured'

    def test_cancel_payment_intent_success(self, stripe_service):
        """Test cancelling payment intent."""
        # Arrange
        payment_intent_id = 'pi_group123'

        mock_intent = MagicMock()
        mock_intent.status = 'cancelled'

        with patch('stripe.PaymentIntent.cancel') as mock_cancel:
            mock_cancel.return_value = mock_intent

            # Act
            result = stripe_service.cancel_payment_intent(payment_intent_id)

        # Assert
        assert result.success is True
        assert result.data['cancelled'] is True
        assert result.data['status'] == 'cancelled'


class TestRefunds:
    """Test refund processing."""

    @pytest.mark.django_db
    def test_process_refund_full_amount(self, stripe_service, test_order):
        """Test processing full refund."""
        # Arrange
        test_order.stripe_payment_intent_id = 'pi_test123'
        test_order.total = Decimal('100.00')
        test_order.status = 'paid'
        test_order.save()

        mock_refund = MagicMock()
        mock_refund.id = 'refund_test123'
        mock_refund.status = 'succeeded'
        mock_refund.created = int(datetime.now().timestamp())

        with patch('stripe.Refund.create') as mock_create:
            mock_create.return_value = mock_refund

            # Act
            result = stripe_service.process_refund(
                order_id=test_order.id,
                reason='requested_by_customer'
            )

        # Assert
        assert result.success is True
        assert result.data['refund_id'] == 'refund_test123'
        assert result.data['amount'] == 10000  # £100 in pence
        assert result.data['status'] == 'succeeded'

        test_order.refresh_from_db()
        assert test_order.status == 'refunded'

        # Verify refund parameters
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['payment_intent'] == 'pi_test123'
        assert call_args['amount'] == 10000
        assert call_args['reason'] == 'requested_by_customer'

    @pytest.mark.django_db
    def test_process_refund_partial_amount(self, stripe_service, test_order):
        """Test processing partial refund."""
        # Arrange
        test_order.stripe_payment_intent_id = 'pi_test123'
        test_order.total = Decimal('100.00')
        test_order.status = 'delivered'
        test_order.save()

        mock_refund = MagicMock()
        mock_refund.id = 'refund_partial123'
        mock_refund.status = 'succeeded'
        mock_refund.created = int(datetime.now().timestamp())

        with patch('stripe.Refund.create') as mock_create:
            mock_create.return_value = mock_refund

            # Act
            result = stripe_service.process_refund(
                order_id=test_order.id,
                amount=Decimal('30.00'),  # Partial refund
                reason='requested_by_customer'
            )

        # Assert
        assert result.success is True
        assert result.data['amount'] == 3000  # £30 in pence

        test_order.refresh_from_db()
        assert test_order.status == 'delivered'  # Status unchanged for partial

        # Verify partial refund amount
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert call_args['amount'] == 3000


class TestVendorBalance:
    """Test vendor balance retrieval."""

    @pytest.mark.django_db
    def test_get_vendor_balance(self, stripe_service, test_vendor):
        """Test retrieving vendor's Stripe balance."""
        # Arrange
        test_vendor.stripe_account_id = 'acct_vendor123'
        test_vendor.save()

        mock_balance = MagicMock()
        mock_balance.available = [
            {'amount': 5000},  # £50
            {'amount': 3000}   # £30
        ]
        mock_balance.pending = [
            {'amount': 2000}   # £20
        ]

        with patch('stripe.Balance.retrieve') as mock_retrieve:
            mock_retrieve.return_value = mock_balance

            # Act
            result = stripe_service.get_vendor_balance(test_vendor)

        # Assert
        assert result.success is True
        assert result.data['available'] == 80.00  # £80 available
        assert result.data['pending'] == 20.00    # £20 pending
        assert result.data['currency'] == 'GBP'

        # Verify it uses vendor's account
        mock_retrieve.assert_called_once_with(stripe_account='acct_vendor123')


class TestWebhookVerification:
    """Test webhook signature verification."""

    def test_verify_webhook_signature_valid(self, stripe_service):
        """Test valid webhook signature verification."""
        # Arrange
        payload = b'{"test": "data"}'
        signature = 'valid_signature'

        mock_event = {'id': 'evt_test123', 'type': 'payment_intent.succeeded'}

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = mock_event

            # Act
            result = stripe_service.verify_webhook_signature(
                payload, signature)

        # Assert
        assert result.success is True
        assert result.data == mock_event

    def test_verify_webhook_signature_invalid(self, stripe_service):
        """Test invalid webhook signature handling."""
        # Arrange
        payload = b'{"test": "data"}'
        signature = 'invalid_signature'

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError(
                'Invalid signature', 'sig_header_value')

            # Act
            result = stripe_service.verify_webhook_signature(
                payload, signature)

        # Assert
        assert result.success is False
        assert result.error_code == 'INVALID_SIGNATURE'
