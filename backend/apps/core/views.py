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

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

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


@extend_schema_view(
    list=extend_schema(
        summary="List users (admin only)",
        description="""
        Retrieve list of users. Admin/staff can see all users, regular users see only themselves.
 
        **Permissions:** Authenticated users (limited to own profile unless staff)
        """,
        tags=['Users']
    ),
    retrieve=extend_schema(
        summary="Get user details",
        description="""
        Retrieve detailed information about a specific user.
 
        **Permissions:** Own profile or admin
        """,
        tags=['Users']
    ),
    create=extend_schema(
        summary="Create user (use /register/ instead)",
        description="""
        Standard user creation endpoint. Consider using /register/ for better flow.
 
        **Permissions:** Public
        """,
        tags=['Users']
    ),
    update=extend_schema(
        summary="Update user profile",
        description="""
        Update all user profile fields.
 
        **Permissions:** Own profile or admin
        """,
        tags=['Users']
    ),
    partial_update=extend_schema(
        summary="Partially update user profile",
        description="""
        Update specific user profile fields.
 
        **Permissions:** Own profile or admin
        """,
        tags=['Users']
    ),
    destroy=extend_schema(
        summary="Delete user (use /delete_account/ instead)",
        description="""
        Delete user account. Consider using /delete_account/ for proper GDPR flow.
 
        **Permissions:** Own profile or admin
        """,
        tags=['Users']
    ),
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

    @extend_schema(
        summary="Register a new user account",
        description="""
        Create a new user account with email and password.
 
        **Process:**
        1. Validates email uniqueness
        2. Creates user account
        3. Generates JWT tokens
        4. Returns user profile and auth tokens
 
        **Example Request:**
```json
        {
            "email": "john@example.com",
            "password": "SecurePass123!",
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": "+44 20 1234 5678"
        }
```
 
        **Permissions:** Public (no authentication required)
        """,
        request=UserRegistrationSerializer,
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'user': {'type': 'object'},
                    'tokens': {'type': 'object'},
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Users']
    )
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

    @extend_schema(
        summary="Login with email and password",
        description="""
        Authenticate user and return JWT tokens.
 
        **Process:**
        1. Validates credentials
        2. Generates JWT access and refresh tokens
        3. Returns user profile and vendor status (if applicable)
 
        **Example Request:**
```json
        {
            "email": "john@example.com",
            "password": "SecurePass123!"
        }
```
 
        **Example Response:**
```json
        {
            "user": {
                "id": 5,
                "email": "john@example.com",
                "first_name": "John",
                "last_name": "Doe"
            },
            "is_vendor": true,
            "vendor": {
                "id": 3,
                "business_name": "John's Farm"
            },
            "tokens": {
                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
            }
        }
```
 
        **Permissions:** Public (no authentication required)
        """,
        request=LoginSerializer,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'user': {'type': 'object'},
                    'is_vendor': {'type': 'boolean'},
                    'vendor': {'type': 'object'},
                    'tokens': {'type': 'object'}
                }
            }
        },
        tags=['Users']
    )
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

    @extend_schema(
        summary="Get current user's profile",
        description="""
        Retrieve the authenticated user's complete profile.
 
        **Includes:**
        - Personal information (email, name, phone)
        - Account settings
        - Vendor status and details (if applicable)
        - Privacy settings
 
        **Permissions:** Authenticated users only
        """,
        responses={200: UserPrivateSerializer},
        tags=['Users']
    )
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get current user's profile.
        GET /api/users/profile/
        """
        serializer = UserPrivateSerializer(request.user)
        return Response(serializer.data)

    @extend_schema(
        summary="Update current user's profile",
        description="""
        Update user profile fields.
 
        **Updatable Fields:**
        - first_name
        - last_name
        - phone_number
        - email (requires verification)
 
        **Example Request:**
```json
        {
            "first_name": "Jane",
            "phone_number": "+44 20 9876 5432"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=UserPrivateSerializer,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'user': {'type': 'object'}
                }
            }
        },
        tags=['Users']
    )
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

    @extend_schema(
        summary="Change user's password",
        description="""
        Change password with current password verification.
 
        **Requirements:**
        - Must provide current password
        - New password must meet security requirements
        - Returns new JWT tokens after password change
 
        **Example Request:**
```json
        {
            "old_password": "OldPass123!",
            "new_password": "NewSecurePass456!"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=PasswordChangeSerializer,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'tokens': {'type': 'object'}
                }
            }
        },
        tags=['Users']
    )
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

    @extend_schema(
        summary="Export user data (GDPR Article 20)",
        description="""
        Export all user data in JSON format for GDPR compliance (Right to Data Portability).
 
        **Includes:**
        - User profile information
        - All orders and transactions
        - Buying group commitments
        - Addresses
        - Privacy settings
        - Activity history
 
        **Response Format:**
        - Content-Type: application/json
        - Downloads as: user-data-{user_id}.json
 
        **GDPR Compliance:**
        - Article 20: Right to data portability
        - Complete data export in machine-readable format
 
        **Permissions:** Authenticated users only
        """,
        responses={
            200: {
                'description': 'JSON file download',
                'content': {
                    'application/json': {
                        'schema': {'type': 'object'}
                    }
                }
            }
        },
        tags=['Users']
    )
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

    @extend_schema(
        summary="Get or update privacy settings",
        description="""
        Manage user privacy preferences.
 
        **Privacy Options:**
        - Email notifications (orders, promotions, newsletters)
        - Profile visibility
        - Data sharing preferences
        - Marketing communications
 
        **GET:** Retrieve current settings
        **PATCH:** Update specific settings
 
        **Example Request (PATCH):**
```json
        {
            "email_notifications": true,
            "marketing_emails": false
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=PrivacySettingsSerializer,
        responses={200: PrivacySettingsSerializer},
        tags=['Users']
    )
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

    @extend_schema(
        summary="Logout user",
        description="""
        Logout by blacklisting the refresh token.
 
        **Process:**
        1. Receives refresh token
        2. Adds token to blacklist
        3. Prevents future token refresh
 
        **Example Request:**
```json
        {
            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
        }
```
 
        **Note:** Access tokens remain valid until expiration. For complete logout, client should delete both tokens.
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'refresh_token': {'type': 'string', 'description': 'JWT refresh token to blacklist'}
                },
                'required': ['refresh_token']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Users']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout user by blacklisting refresh token.
        POST /api/users/logout/
        """
        try:
            refresh_token = request.data.get('refresh_token')

            if not refresh_token:
                return Response(
                    {'error': 'refresh_token is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Blacklist the token
            token = RefreshToken(refresh_token)

            # Check if already blacklisted or handle other errors
            try:
                token.blacklist()
            except Exception as e:
                # Token already blacklisted or other error - ignore
                pass

            return Response({'message': 'Logged out successfully'})

        except Exception as e:
            return Response(
                {'error': 'Invalid token'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @extend_schema(
        summary="Delete user account (GDPR Article 17)",
        description="""
        Permanently delete user account and all associated data (Right to Erasure).
 
        **Requirements:**
        - Password confirmation required
        - No active orders or commitments
        - Vendors must complete all pending orders first
 
        **Process:**
        1. Validates password
        2. Checks for active orders/commitments
        3. Permanently deletes account and data
        4. Cascades deletion to related data
 
        **GDPR Compliance:**
        - Article 17: Right to erasure ("right to be forgotten")
        - Complete data deletion
 
        **Example Request:**
```json
        {
            "password": "YourPassword123!"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'password': {'type': 'string', 'description': 'Current password for confirmation'}
                },
                'required': ['password']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Users']
    )
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


@extend_schema_view(
    list=extend_schema(
        summary="List user's addresses",
        description="""
        Retrieve all delivery addresses for the authenticated user.
 
        **Includes:**
        - Full address details
        - Default address indicator
        - Geocoded location data
 
        **Permissions:** Authenticated users only
        """,
        tags=['Addresses']
    ),
    retrieve=extend_schema(
        summary="Get address details",
        description="""
        Retrieve detailed information about a specific address.
 
        **Permissions:** Address owner only
        """,
        tags=['Addresses']
    ),
    create=extend_schema(
        summary="Create a new address",
        description="""
        Add a new delivery address to user's address book.
 
        **Process:**
        1. Validates UK postcode format
        2. Geocodes postcode to get coordinates
        3. Stores address with location data
        4. Can be set as default address
 
        **Example Request:**
```json
        {
            "label": "Home",
            "street_address": "123 Main Street",
            "city": "London",
            "postcode": "SW1A 1AA",
            "is_default": true
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request=AddressSerializer,
        responses={201: AddressSerializer},
        tags=['Addresses']
    ),
    update=extend_schema(
        summary="Update address",
        description="""
        Update all fields of an address.
 
        **Permissions:** Address owner only
        """,
        tags=['Addresses']
    ),
    partial_update=extend_schema(
        summary="Partially update address",
        description="""
        Update specific fields of an address.
 
        **Permissions:** Address owner only
        """,
        tags=['Addresses']
    ),
    destroy=extend_schema(
        summary="Delete address",
        description="""
        Remove an address from the user's address book.
 
        **Permissions:** Address owner only
        """,
        tags=['Addresses']
    ),
)
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

    @extend_schema(
        summary="Set address as default",
        description="""
        Mark an address as the default delivery address.
 
        **Process:**
        1. Unsets current default address (if any)
        2. Sets this address as default
        3. Returns updated address
 
        **Use Cases:**
        - Quick checkout with default address
        - Primary delivery location
 
        **Permissions:** Address owner only
        """,
        responses={200: AddressSerializer},
        tags=['Addresses']
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

    @extend_schema(
        summary="Get default address",
        description="""
        Retrieve the user's default delivery address.
 
        **Returns:**
        - Default address if set
        - First address if no default set
        - 404 if no addresses exist
 
        **Use Cases:**
        - Pre-fill checkout forms
        - Quick order placement
        - Default delivery selection
 
        **Permissions:** Authenticated users only
        """,
        responses={
            200: AddressSerializer,
            404: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Addresses']
    )
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
