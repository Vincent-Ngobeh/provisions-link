"""
API tests for core endpoints.
Tests authentication, user management, and GDPR compliance.
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.urls import reverse

from apps.core.models import User, Address, PrivacySettings
from tests.conftest import UserFactory, AddressFactory


@pytest.mark.django_db
class TestUserRegistrationAPI:
    """Test user registration endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('user-register')

    def test_successful_registration(self):
        """Test successful user registration."""
        data = {
            'email': 'newuser@example.com',
            'username': 'newuser',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone_number': '+447123456789'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert 'user' in response.data
        assert 'tokens' in response.data
        assert response.data['user']['email'] == 'newuser@example.com'

        # Verify user was created
        user = User.objects.get(email='newuser@example.com')
        assert user.username == 'newuser'

        # Verify privacy settings were created
        assert hasattr(user, 'privacy_settings')

    def test_registration_password_mismatch(self):
        """Test that mismatched passwords are rejected."""
        data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'Password123!',
            'password_confirm': 'DifferentPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in str(response.data).lower()

    def test_registration_duplicate_email(self):
        """Test that duplicate emails are rejected."""
        UserFactory(email='existing@example.com')

        data = {
            'email': 'existing@example.com',
            'username': 'newusername',
            'password': 'Password123!',
            'password_confirm': 'Password123!',
            'first_name': 'Test',
            'last_name': 'User'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in str(response.data).lower()

    def test_registration_weak_password(self):
        """Test that weak passwords are rejected."""
        data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': '1234',  # Too short
            'password_confirm': '1234',
            'first_name': 'Test',
            'last_name': 'User'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in str(response.data).lower()


@pytest.mark.django_db
class TestUserLoginAPI:
    """Test user login endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.url = reverse('user-login')
        self.user = UserFactory(
            email='test@example.com',
            username='testuser',
            password='Testpass123!',
        )
        self.user.set_password('TestPass123!')
        self.user.save()

    def test_login_with_email(self):
        """Test login using email."""
        data = {
            'email_or_username': 'test@example.com',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        assert 'tokens' in response.data
        assert 'user' in response.data
        assert response.data['user']['email'] == 'test@example.com'

    def test_login_with_username(self):
        """Test login using username."""
        data = {
            'email_or_username': 'testuser',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        assert 'tokens' in response.data

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        data = {
            'email_or_username': 'test@example.com',
            'password': 'WrongPassword'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'invalid' in str(response.data).lower()

    def test_login_returns_vendor_info(self):
        """Test that login returns vendor info if user has vendor account."""
        from tests.conftest import VendorFactory
        vendor = VendorFactory(user=self.user)

        data = {
            'email_or_username': 'test@example.com',
            'password': 'TestPass123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_vendor'] is True
        assert response.data['vendor']['id'] == vendor.id


@pytest.mark.django_db
class TestUserProfileAPI:
    """Test user profile endpoints."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.url = reverse('user-profile')

    def test_get_profile_requires_auth(self):
        """Test that profile endpoint requires authentication."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_own_profile(self):
        """Test getting authenticated user's profile."""
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == self.user.id
        assert response.data['email'] == self.user.email

    def test_update_profile(self):
        """Test updating user profile."""
        self.client.force_authenticate(self.user)
        url = reverse('user-update-profile')

        data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'phone_number': '+447987654321'
        }

        response = self.client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK

        self.user.refresh_from_db()
        assert self.user.first_name == 'Updated'
        assert self.user.last_name == 'Name'

    def test_cannot_update_email_via_profile(self):
        """Test that email cannot be changed via profile update."""
        self.client.force_authenticate(self.user)
        url = reverse('user-update-profile')

        data = {'email': 'newemail@example.com'}

        response = self.client.patch(url, data)

        self.user.refresh_from_db()
        assert self.user.email != 'newemail@example.com'  # Should not change


@pytest.mark.django_db
class TestPasswordChangeAPI:
    """Test password change endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.user.set_password('OldPassword123!')
        self.user.save()
        self.url = reverse('user-change-password')

    def test_change_password_success(self):
        """Test successful password change."""
        self.client.force_authenticate(self.user)

        data = {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'NewPassword123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_200_OK
        assert 'tokens' in response.data  # New tokens issued

        # Verify password was changed
        self.user.refresh_from_db()
        assert self.user.check_password('NewPassword123!')

    def test_change_password_wrong_old_password(self):
        """Test that wrong old password is rejected."""
        self.client.force_authenticate(self.user)

        data = {
            'old_password': 'WrongOldPassword',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'NewPassword123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'incorrect' in str(response.data).lower()

    def test_change_password_mismatch(self):
        """Test that new password mismatch is rejected."""
        self.client.force_authenticate(self.user)

        data = {
            'old_password': 'OldPassword123!',
            'new_password': 'NewPassword123!',
            'new_password_confirm': 'DifferentPassword123!'
        }

        response = self.client.post(self.url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "don't match" in str(response.data).lower()


@pytest.mark.django_db
class TestGDPRExportAPI:
    """Test GDPR data export endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.url = reverse('user-export-data')

    def test_export_user_data(self):
        """Test exporting all user data."""
        self.client.force_authenticate(self.user)

        # Create some user data
        AddressFactory(user=self.user)
        from tests.conftest import OrderFactory, VendorFactory
        vendor = VendorFactory(user=self.user)
        OrderFactory(buyer=self.user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/json'
        assert 'attachment' in response['Content-Disposition']

        # Parse JSON response
        import json
        data = json.loads(response.content)

        assert 'user_profile' in data
        assert 'addresses' in data
        assert 'orders' in data
        assert 'vendor_profile' in data
        assert data['user_profile']['id'] == self.user.id

    def test_export_requires_authentication(self):
        """Test that data export requires authentication."""
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestPrivacySettingsAPI:
    """Test privacy settings endpoint."""

    def setup_method(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.url = reverse('user-privacy-settings')
        # Create privacy settings
        PrivacySettings.objects.create(user=self.user)

    def test_get_privacy_settings(self):
        """Test getting privacy settings."""
        self.client.force_authenticate(self.user)

        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert 'marketing_emails' in response.data
        assert 'order_updates' in response.data
        assert 'data_sharing' in response.data

    def test_update_privacy_settings(self):
        """Test updating privacy settings."""
        self.client.force_authenticate(self.user)

        data = {
            'marketing_emails': True,
            'data_sharing': False
        }

        response = self.client.patch(self.url, data)

        assert response.status_code == status.HTTP_200_OK

        settings = PrivacySettings.objects.get(user=self.user)
        assert settings.marketing_emails is True
        assert settings.data_sharing is False
