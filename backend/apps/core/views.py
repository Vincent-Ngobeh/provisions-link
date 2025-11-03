"""
ViewSet implementations for core operations.
Handles authentication, user management, and GDPR compliance.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.http import HttpResponse
import json

from .models import User, Address, PrivacySettings
from .serializers import (
    UserPublicSerializer,
    UserPrivateSerializer,
    UserRegistrationSerializer,
    AddressSerializer,
    PrivacySettingsSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    GDPRExportSerializer
)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user operations.
    Handles registration, profile management, and GDPR compliance.
    """
    queryset = User.objects.all()
    serializer_class = UserPublicSerializer

    def get_permissions(self):
        """Configure permissions per action."""
        if self.action in ['create', 'register', 'login']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'register':
            return UserRegistrationSerializer
        elif self.action in ['profile', 'update_profile']:
            return UserPrivateSerializer
        elif self.action == 'change_password':
            return PasswordChangeSerializer
        return self.serializer_class

    def get_queryset(self):
        """Users can only see their own data unless staff."""
        if self.request.user.is_staff:
            return super().get_queryset()
        return super().get_queryset().filter(id=self.request.user.id)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """
        Register a new user account.
        POST /api/users/register/
        """
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'user': UserPrivateSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            },
            'message': 'Registration successful'
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        """
        Custom login endpoint with email or username.
        POST /api/users/login/
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        # Generate tokens
        refresh = RefreshToken.for_user(user)

        # Check if user has vendor account
        is_vendor = hasattr(user, 'vendor')
        vendor_data = None
        if is_vendor:
            from apps.vendors.serializers import VendorListSerializer
            vendor_data = VendorListSerializer(user.vendor).data

        return Response({
            'user': UserPrivateSerializer(user).data,
            'is_vendor': is_vendor,
            'vendor': vendor_data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            }
        })

    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get current user's profile.
        GET /api/users/profile/
        """
        serializer = UserPrivateSerializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        """
        Update current user's profile.
        PATCH /api/users/update_profile/
        """
        serializer = UserPrivateSerializer(
            request.user,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Profile updated successfully',
            'user': serializer.data
        })

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """
        Change user's password.
        POST /api/users/change_password/
        """
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        # Generate new tokens
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Password changed successfully',
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token)
            }
        })

    @action(detail=False, methods=['get'])
    def export_data(self, request):
        """
        GDPR Article 20 - Export all user data.
        GET /api/users/export_data/
        """
        serializer = GDPRExportSerializer()
        data = serializer.to_representation(request.user)

        # Create downloadable JSON file
        response = HttpResponse(
            json.dumps(data, indent=2, default=str),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="user-data-{request.user.id}.json"'

        return response

    @action(detail=False, methods=['get', 'patch'])
    def privacy_settings(self, request):
        """
        Get or update privacy settings.
        GET/PATCH /api/users/privacy_settings/
        """
        settings, created = PrivacySettings.objects.get_or_create(
            user=request.user
        )

        if request.method == 'GET':
            serializer = PrivacySettingsSerializer(settings)
            return Response(serializer.data)

        # PATCH
        serializer = PrivacySettingsSerializer(
            settings,
            data=request.data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Privacy settings updated',
            'settings': serializer.data
        })

    @action(detail=False, methods=['post'])
    def logout(self, request):
        """
        Logout user (blacklist refresh token).
        POST /api/users/logout/
        """
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({
                'message': 'Logout successful'
            })
        except Exception:
            return Response({
                'message': 'Logout successful'
            })

    @action(detail=False, methods=['post'])
    def delete_account(self, request):
        """
        Delete user account (GDPR Article 17 - Right to Erasure).
        POST /api/users/delete_account/

        Requires password confirmation for security.
        """
        password = request.data.get('password')

        if not password:
            return Response({
                'error': 'Password confirmation required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify password
        if not request.user.check_password(password):
            return Response({
                'error': 'Incorrect password'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if user has active vendor account
        if hasattr(request.user, 'vendor'):
            # Check for pending orders
            from apps.orders.models import Order
            pending_orders = Order.objects.filter(
                vendor=request.user.vendor,
                status__in=['pending', 'paid', 'processing', 'shipped']
            ).exists()

            if pending_orders:
                return Response({
                    'error': 'Cannot delete account with pending vendor orders. Please complete or cancel all orders first.'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Check for active buyer orders
        from apps.orders.models import Order
        active_orders = Order.objects.filter(
            buyer=request.user,
            status__in=['pending', 'paid', 'processing', 'shipped']
        ).exists()

        if active_orders:
            return Response({
                'error': 'Cannot delete account with active orders. Please wait for orders to complete or contact support.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check for active group commitments
        from apps.buying_groups.models import GroupCommitment
        active_commitments = GroupCommitment.objects.filter(
            buyer=request.user,
            status='pending'
        ).exists()

        if active_commitments:
            return Response({
                'error': 'Cannot delete account with active group commitments. Please cancel your commitments first.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Store email for response
        user_email = request.user.email

        # Perform deletion
        try:
            request.user.delete()

            return Response({
                'message': f'Account {user_email} has been permanently deleted.'
            })
        except Exception as e:
            return Response({
                'error': 'Failed to delete account. Please contact support.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AddressViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user addresses.
    Handles delivery address management.
    """
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Users can only see their own addresses."""
        return super().get_queryset().filter(user=self.request.user)

    def perform_create(self, serializer):
        """Associate address with current user."""
        # Geocode the address
        from apps.integrations.services.geocoding_service import GeocodingService
        geo_service = GeocodingService()

        postcode = serializer.validated_data['postcode']
        result = geo_service.geocode_postcode(postcode)

        location = None
        if result.success:
            location = result.data['point']

        serializer.save(
            user=self.request.user,
            location=location
        )

    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """
        Set an address as default.
        POST /api/addresses/{id}/set_default/
        """
        address = self.get_object()

        # Unset other defaults
        Address.objects.filter(
            user=request.user,
            is_default=True
        ).update(is_default=False)

        # Set this as default
        address.is_default = True
        address.save()

        return Response({
            'message': 'Default address updated',
            'address': AddressSerializer(address).data
        })

    @action(detail=False, methods=['get'])
    def default(self, request):
        """
        Get user's default address.
        GET /api/addresses/default/
        """
        address = Address.objects.filter(
            user=request.user,
            is_default=True
        ).first()

        if not address:
            address = Address.objects.filter(user=request.user).first()

        if address:
            serializer = AddressSerializer(address)
            return Response(serializer.data)

        return Response({
            'message': 'No addresses found'
        }, status=status.HTTP_404_NOT_FOUND)
