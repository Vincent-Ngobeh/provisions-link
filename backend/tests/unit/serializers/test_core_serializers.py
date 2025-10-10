"""
Tests for core serializers.
Tests user registration, authentication, and GDPR data export.
"""
import pytest
from rest_framework.exceptions import ValidationError

from apps.core.serializers import (
    UserRegistrationSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    AddressSerializer,
    PrivacySettingsSerializer,
    GDPRExportSerializer
)
from apps.core.models import User, Address, PrivacySettings
from tests.conftest import UserFactory, AddressFactory


@pytest.mark.django_db
class TestUserRegistrationSerializer:
    """Test user registration serializer."""

    def test_valid_registration_data(self):
        """Test serializer accepts valid registration data."""
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'SecurePassword123!',
            'password_confirm': 'SecurePassword123!',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+447123456789'
        }

        serializer = UserRegistrationSerializer(data=data)

        assert serializer.is_valid()
        validated = serializer.validated_data
        assert validated['email'] == 'newuser@example.com'
        assert 'password_confirm' not in validated  # Removed after validation

    def test_password_confirmation_mismatch(self):
        """Test that password confirmation must match."""
        data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'Password123!',
            'password_confirm': 'DifferentPassword123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert "don't match" in str(serializer.errors).lower()

    def test_password_minimum_length(self):
        """Test that password must meet minimum length."""
        data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'Short1!',  # Less than 8 chars
            'password_confirm': 'Short1!',
            'first_name': 'Test',
            'last_name': 'User'
        }

        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert 'password' in serializer.errors

    def test_email_uniqueness(self):
        """Test that email must be unique."""
        UserFactory(email='existing@example.com')

        data = {
            'email': 'existing@example.com',  # Already exists
            'username': 'newuser',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

        serializer = UserRegistrationSerializer(data=data)

        assert not serializer.is_valid()
        assert 'email' in serializer.errors

    def test_creates_privacy_settings(self):
        """Test that registration creates privacy settings."""
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'first_name': 'John',
            'last_name': 'Doe'
        }

        serializer = UserRegistrationSerializer(data=data)
        assert serializer.is_valid()

        user = serializer.save()

        # Check user was created with password
        assert user.email == 'newuser@example.com'
        assert user.check_password('Password123!')

        # Check privacy settings were created
        assert PrivacySettings.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestLoginSerializer:
    """Test login serializer."""

    def setup_method(self):
        self.user = UserFactory(
            email='test@example.com',
            username='testuser'
        )
        self.user.set_password('TestPassword123!')
        self.user.save()

    def test_login_with_email(self):
        """Test login using email."""
        data = {
            'email_or_username': 'test@example.com',
            'password': 'TestPassword123!'
        }

        serializer = LoginSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data['user'] == self.user

    def test_login_with_username(self):
        """Test login using username."""
        data = {
            'email_or_username': 'testuser',
            'password': 'TestPassword123!'
        }

        serializer = LoginSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data['user'] == self.user

    def test_login_invalid_credentials(self):
        """Test login with wrong password."""
        data = {
            'email_or_username': 'test@example.com',
            'password': 'WrongPassword!'
        }

        serializer = LoginSerializer(data=data)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert 'invalid' in str(serializer.errors).lower()

    def test_login_nonexistent_user(self):
        """Test login with non-existent user."""
        data = {
            'email_or_username': 'nonexistent@example.com',
            'password': 'Password123!'
        }

        serializer = LoginSerializer(data=data)

        assert not serializer.is_valid()
        assert 'invalid' in str(serializer.errors).lower()


@pytest.mark.django_db
class TestPasswordChangeSerializer:
    """Test password change serializer."""

    def setup_method(self):
        self.user = UserFactory()
        self.user.set_password('OldPassword123!')
        self.user.save()
        self.context = {'request': type('Request', (), {'user': self.user})()}

    def test_valid_password_change(self):
        """Test valid password change."""
        data = {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'NewPassword123!'
        }

        serializer = PasswordChangeSerializer(data=data, context=self.context)

        assert serializer.is_valid()

    def test_incorrect_old_password(self):
        """Test that old password must be correct."""
        data = {
            'old_password': 'WrongOldPassword!',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'NewPassword123!'
        }

        serializer = PasswordChangeSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'old_password' in serializer.errors
        assert 'incorrect' in str(serializer.errors['old_password'][0]).lower()

    def test_new_password_mismatch(self):
        """Test that new passwords must match."""
        data = {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'DifferentPassword123!'
        }

        serializer = PasswordChangeSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'non_field_errors' in serializer.errors
        assert "don't match" in str(serializer.errors).lower()

    def test_new_password_minimum_length(self):
        """Test that new password meets minimum length."""
        data = {
            'old_password': 'OldPassword123!',
            'new_password': 'Short1!',
            'new_password_confirm': 'Short1!'
        }

        serializer = PasswordChangeSerializer(data=data, context=self.context)

        assert not serializer.is_valid()
        assert 'new_password' in serializer.errors


@pytest.mark.django_db
class TestAddressSerializer:
    """Test address serializer."""

    def test_valid_address_data(self):
        """Test serializer accepts valid address data."""
        data = {
            'address_name': 'home',
            'recipient_name': 'John Doe',
            'phone_number': '+447123456789',
            'line1': '123 High Street',
            'line2': 'Flat 4',
            'city': 'London',
            'postcode': 'SW1A 1AA',
            'country': 'GB',
            'is_default': True
        }

        serializer = AddressSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data['postcode'] == 'SW1A 1AA'

    def test_postcode_validation(self):
        """Test UK postcode format validation."""
        invalid_postcodes = [
            'INVALID',
            '12345',  # US ZIP
            'sw1a1aa1',  # Too long
            'ABC 123'
        ]

        for postcode in invalid_postcodes:
            data = {
                'address_name': 'Test',
                'recipient_name': 'Test User',
                'phone_number': '+447123456789',
                'line1': '123 Test Street',
                'city': 'London',
                'postcode': postcode,
                'country': 'GB'
            }

            serializer = AddressSerializer(data=data)

            assert not serializer.is_valid()
            assert 'postcode' in serializer.errors

    def test_postcode_normalization(self):
        """Test that postcodes are normalized to uppercase."""
        data = {
            'address_name': 'home',
            'recipient_name': 'John Doe',
            'phone_number': '+447123456789',
            'line1': '123 High Street',
            'city': 'London',
            'postcode': 'sw1a 1aa',
            'country': 'GB'
        }

        serializer = AddressSerializer(data=data)

        assert serializer.is_valid()
        assert serializer.validated_data['postcode'] == 'SW1A 1AA'


@pytest.mark.django_db
class TestPrivacySettingsSerializer:
    """Test privacy settings serializer."""

    def test_all_privacy_fields(self):
        """Test all privacy fields are included."""
        user = UserFactory()
        settings = PrivacySettings.objects.create(
            user=user,
            marketing_emails=True,
            order_updates=True,
            data_sharing=False,
            analytics_tracking=False
        )

        serializer = PrivacySettingsSerializer(settings)
        data = serializer.data

        assert data['marketing_emails'] is True
        assert data['order_updates'] is True
        assert data['data_sharing'] is False
        assert data['analytics_tracking'] is False
        assert 'updated_at' in data

    def test_partial_update(self):
        """Test partial update of privacy settings."""
        user = UserFactory()
        settings = PrivacySettings.objects.create(user=user)

        data = {
            'marketing_emails': True,
            'analytics_tracking': True
        }

        serializer = PrivacySettingsSerializer(
            settings,
            data=data,
            partial=True
        )

        assert serializer.is_valid()
        serializer.save()

        settings.refresh_from_db()
        assert settings.marketing_emails is True
        assert settings.analytics_tracking is True


@pytest.mark.django_db
class TestGDPRExportSerializer:
    """Test GDPR data export serializer."""

    def test_exports_all_user_data(self):
        """Test that all user data is exported."""
        from tests.conftest import VendorFactory, OrderFactory, GroupCommitmentFactory

        user = UserFactory()
        address = AddressFactory(user=user)
        privacy_settings = PrivacySettings.objects.create(user=user)
        vendor = VendorFactory(user=user)
        order = OrderFactory(buyer=user)

        serializer = GDPRExportSerializer()
        data = serializer.to_representation(user)

        # Check all sections are present
        assert 'exported_at' in data
        assert 'user_profile' in data
        assert 'privacy_settings' in data
        assert 'addresses' in data
        assert 'vendor_profile' in data
        assert 'orders' in data

        # Check data is correctly included
        assert data['user_profile']['id'] == user.id
        assert len(data['addresses']) == 1
        assert data['addresses'][0]['id'] == address.id
        assert data['vendor_profile']['id'] == vendor.id
        assert len(data['orders']) == 1

    def test_export_without_vendor_account(self):
        """Test export for users without vendor account."""
        user = UserFactory()
        PrivacySettings.objects.create(user=user)

        serializer = GDPRExportSerializer()
        data = serializer.to_representation(user)

        # Vendor profile should be None
        assert data['vendor_profile'] is None

        # Other data should still be present
        assert 'user_profile' in data
        assert 'privacy_settings' in data
