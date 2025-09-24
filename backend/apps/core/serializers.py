# apps/core/serializers.py

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from .models import Address, PrivacySettings

User = get_user_model()


class UserPublicSerializer(serializers.ModelSerializer):
    """Minimal user info for public display (e.g., in reviews, group participants)"""

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name']
        read_only_fields = fields


class AddressSerializer(serializers.ModelSerializer):
    """Address serializer for delivery locations"""

    class Meta:
        model = Address
        fields = [
            'id', 'address_name', 'recipient_name', 'phone_number',
            'line1', 'line2', 'city', 'postcode', 'country',
            'is_default', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate_postcode(self, value):
        """Ensure UK postcode format"""
        # Basic UK postcode validation
        import re
        pattern = r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$'
        if not re.match(pattern, value.upper()):
            raise serializers.ValidationError("Invalid UK postcode format")
        return value.upper()


class UserPrivateSerializer(serializers.ModelSerializer):
    """Full user info for authenticated user's own profile"""
    addresses = AddressSerializer(many=True, read_only=True)
    has_vendor_account = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone_number', 'date_joined', 'addresses', 'has_vendor_account'
        ]
        read_only_fields = ['id', 'email', 'date_joined']

    def get_has_vendor_account(self, obj):
        return hasattr(obj, 'vendor')


class UserRegistrationSerializer(serializers.ModelSerializer):
    """User registration with password handling"""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone_number'
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError("Passwords don't match")
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        # Create privacy settings with defaults
        PrivacySettings.objects.create(user=user)
        return user


class PrivacySettingsSerializer(serializers.ModelSerializer):
    """GDPR-compliant privacy settings"""

    class Meta:
        model = PrivacySettings
        fields = [
            'marketing_emails', 'order_updates',
            'data_sharing', 'analytics_tracking', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token with additional user data"""

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserPrivateSerializer(self.user).data
        data['is_vendor'] = hasattr(self.user, 'vendor')
        if hasattr(self.user, 'vendor'):
            data['vendor_id'] = self.user.vendor.id
        return data


class LoginSerializer(serializers.Serializer):
    """Login with email or username"""
    email_or_username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        from django.contrib.auth import authenticate
        from django.db.models import Q

        identifier = attrs.get('email_or_username')
        password = attrs.get('password')

        # Try to find user by email or username
        User = get_user_model()
        try:
            user = User.objects.get(
                Q(email=identifier) | Q(username=identifier)
            )
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")

        # Authenticate
        user = authenticate(username=user.username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials")

        attrs['user'] = user
        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    """Change password for authenticated user"""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match")
        return attrs
