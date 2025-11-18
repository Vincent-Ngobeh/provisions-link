"""
ViewSet implementations for group buying operations.
Handles group creation, commitments, and real-time updates.
"""
import logging
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, F, Count
from django.utils import timezone

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

from .models import BuyingGroup, GroupCommitment, GroupUpdate
from .serializers import (
    BuyingGroupListSerializer,
    BuyingGroupDetailSerializer,
    BuyingGroupCreateSerializer,
    GroupCommitmentSerializer,
    BuyingGroupRealtimeSerializer
)
from .services.group_buying_service import GroupBuyingService
from apps.core.models import Address

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        summary="List all buying groups",
        description="""
        Retrieve a list of buying groups with filtering capabilities.
 
        **Includes:**
        - Product details and vendor information
        - Current progress (participants count, target quantity)
        - Discount percentage and pricing
        - Geographic coverage (postcode and radius)
        - Expiration date and status
 
        **Filtering:**
        - Filter by status (open, active, closed, cancelled)
        - Filter by product ID
        - Hide/show expired groups
 
        **Permissions:** Public (no authentication required)
        """,
        parameters=[
            OpenApiParameter(
                name='status',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by status (supports comma-separated values: open,active)',
                examples=[
                    OpenApiExample('Open groups', value='open'),
                    OpenApiExample('Multiple statuses', value='open,active'),
                ]
            ),
            OpenApiParameter(
                name='product',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by product ID'
            ),
            OpenApiParameter(
                name='hide_expired',
                type=Types.BOOL,
                location=OpenApiParameter.QUERY,
                description='Hide expired groups (default: true)'
            ),
        ],
        tags=['Buying Groups']
    ),
    retrieve=extend_schema(
        summary="Get buying group details",
        description="""
        Retrieve detailed information about a specific buying group.
 
        **Includes:**
        - Full product and vendor details
        - List of current participants (anonymized)
        - Progress percentage and remaining quantity
        - Geographic center point and delivery radius
        - Commitment history and updates
 
        **Permissions:** Public (no authentication required)
        """,
        tags=['Buying Groups']
    ),
    create=extend_schema(
        summary="Create a buying group (use create_group instead)",
        description="""
        Standard create endpoint. Consider using /create_group/ for better validation.
 
        **Permissions:** Authenticated users only
        """,
        tags=['Buying Groups']
    ),
    update=extend_schema(
        summary="Update buying group",
        description="""
        Update buying group details (admin only).
 
        **Permissions:** Admin/staff only
        """,
        tags=['Buying Groups']
    ),
    partial_update=extend_schema(
        summary="Partially update buying group",
        description="""
        Partially update buying group fields (admin only).
 
        **Permissions:** Admin/staff only
        """,
        tags=['Buying Groups']
    ),
    destroy=extend_schema(
        summary="Delete buying group",
        description="""
        Cancel and delete a buying group (admin only).
 
        **Permissions:** Admin/staff only
        """,
        tags=['Buying Groups']
    ),
)
class BuyingGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for buying group operations.
    Manages group lifecycle and real-time updates.
    """
    queryset = BuyingGroup.objects.all()
    serializer_class = BuyingGroupListSerializer
    service = GroupBuyingService()

    def get_permissions(self):
        """Configure permissions per action."""
        if self.action in ['list', 'retrieve', 'active_groups', 'near_me', 'realtime_status']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return BuyingGroupDetailSerializer
        elif self.action == 'create':
            return BuyingGroupCreateSerializer
        elif self.action in ['realtime_status', 'subscribe']:
            return BuyingGroupRealtimeSerializer
        return self.serializer_class

    def get_queryset(self):
        """
        Filter and optimize queryset.

        FIX 5: CRITICAL - Always annotate participants_count for ALL actions,
        including 'retrieve' (detail view). Previously, this annotation may have
        been conditionally applied only for list views, causing detail pages to
        show 0 participants and 0% progress.
        """
        queryset = super().get_queryset().select_related(
            'product__vendor', 'product__category'
        ).annotate(
            # ALWAYS annotate participants_count - needed for both list AND detail views
            participants_count=Count(
                'commitments',
                filter=Q(commitments__status='pending')
            )
        )
        # NOTE: No conditional wrapping around the annotation above!
        # It must be applied to all queries regardless of action.

        # Filter by status (supports comma-separated values for multiple statuses)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            # Support filtering by multiple statuses: ?status=open,active
            statuses = [s.strip() for s in status_filter.split(',')]
            queryset = queryset.filter(status__in=statuses)

        # Filter by product
        product_id = self.request.query_params.get('product')
        if product_id:
            queryset = queryset.filter(product_id=product_id)

        # Don't filter expired groups for actions that need to handle them
        # (like commit, which needs to show proper validation error)
        if self.action not in ['commit', 'cancel_commitment', 'retrieve']:
            hide_expired = self.request.query_params.get(
                'hide_expired', 'true').lower() == 'true'
            if hide_expired:
                queryset = queryset.filter(expires_at__gt=timezone.now())

        return queryset.order_by('-created_at')

    @extend_schema(
        summary="Create a new buying group",
        description="""
        Create a buying group for collective purchasing in a specific area.
 
        **Process:**
        1. Validates product availability
        2. Geocodes the postcode to set group center point
        3. Sets discount percentage and target quantity
        4. Opens group for commitments
        5. Sets expiration date based on duration
 
        **Requirements:**
        - Product must be active and in stock
        - Valid UK postcode
        - Target quantity (optional - auto-calculated if not provided)
        - Duration in days (default: 7)
 
        **Example Request:**
```json
        {
            "product_id": 15,
            "postcode": "E2 7DJ",
            "target_quantity": 50,
            "discount_percent": 15.00,
            "duration_days": 7,
            "radius_km": 5
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'product_id': {'type': 'integer', 'description': 'Product ID'},
                    'postcode': {'type': 'string', 'description': 'UK postcode for group center'},
                    'target_quantity': {'type': 'integer', 'description': 'Target quantity to unlock discount'},
                    'discount_percent': {'type': 'number', 'format': 'decimal', 'description': 'Discount percentage (e.g., 15.00)'},
                    'duration_days': {'type': 'integer', 'description': 'Group duration in days (default: 7)'},
                    'radius_km': {'type': 'integer', 'description': 'Delivery radius in km (default: 5)'}
                },
                'required': ['product_id', 'postcode']
            }
        },
        responses={201: BuyingGroupDetailSerializer},
        tags=['Buying Groups']
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def create_group(self, request):
        """
        Create a new buying group.
        POST /api/buying-groups/create_group/
        """
        product_id = request.data.get('product_id')
        postcode = request.data.get('postcode')
        target_quantity = request.data.get('target_quantity')
        discount_percent = request.data.get('discount_percent')
        duration_days = request.data.get('duration_days', 7)
        radius_km = request.data.get('radius_km', 5)

        if not all([product_id, postcode]):
            return Response({
                'error': 'product_id and postcode are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Convert discount_percent to Decimal if provided
        if discount_percent:
            try:
                discount_percent = Decimal(str(discount_percent))
            except (ValueError, TypeError):
                return Response({
                    'error': 'Invalid discount_percent format'
                }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.create_group_for_area(
            product_id=int(product_id),
            postcode=postcode,
            target_quantity=int(target_quantity) if target_quantity else None,
            discount_percent=discount_percent,
            duration_days=int(duration_days),
            radius_km=int(radius_km)
        )

        if result.success:
            serializer = BuyingGroupDetailSerializer(result.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Create payment intent for group commitment (Step 1)",
        description="""
        Create a Stripe payment intent for joining a buying group without committing yet.
        This is step 1 of the two-step payment flow.
 
        **Process:**
        1. Validates buyer's address is within group radius
        2. Calculates total amount with discount
        3. Creates Stripe payment intent
        4. Returns client secret for frontend payment confirmation
 
        **Flow:**
        - Step 1: Call this endpoint to get payment intent
        - Step 2: Confirm payment on frontend with Stripe.js
        - Step 3: Call /commit/ with confirmed payment_intent_id
 
        **Example Request:**
```json
        {
            "quantity": 5,
            "postcode": "E2 7DJ",
            "delivery_address_id": 12
        }
```
 
        **Example Response:**
```json
        {
            "client_secret": "pi_xxx_secret_xxx",
            "intent_id": "pi_xxx",
            "amount": 117.56
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'quantity': {'type': 'integer', 'description': 'Quantity to purchase'},
                    'postcode': {'type': 'string', 'description': 'Delivery postcode'},
                    'delivery_address_id': {'type': 'integer', 'description': 'Delivery address ID'}
                },
                'required': ['quantity', 'postcode', 'delivery_address_id']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'client_secret': {'type': 'string'},
                    'intent_id': {'type': 'string'},
                    'amount': {'type': 'number', 'format': 'float'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def create_payment_intent(self, request, pk=None):
        """
        Create a payment intent for a group commitment WITHOUT creating the commitment.
        This is step 1 of the two-step payment flow.
        POST /api/buying-groups/{id}/create_payment_intent/

        Body:
        {
            "quantity": 5,
            "postcode": "E2 7DJ",
            "delivery_address_id": 12
        }

        Returns:
        {
            "client_secret": "pi_xxx_secret_xxx",
            "intent_id": "pi_xxx",
            "amount": 117.56
        }
        """
        group = self.get_object()

        quantity = request.data.get('quantity')
        buyer_postcode = request.data.get('postcode')
        delivery_address_id = request.data.get('delivery_address_id')

        if not all([quantity, buyer_postcode, delivery_address_id]):
            return Response({
                'error': 'quantity, postcode, and delivery_address_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.create_payment_intent_for_commitment(
            group_id=group.id,
            buyer=request.user,
            quantity=int(quantity),
            buyer_postcode=buyer_postcode,
            delivery_address_id=int(delivery_address_id)
        )

        if result.success:
            return Response({
                'client_secret': result.data['client_secret'],
                'intent_id': result.data['intent_id'],
                'amount': float(result.data['amount'])
            }, status=status.HTTP_200_OK)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Commit to a buying group (Step 2)",
        description="""
        Join a buying group after payment confirmation. This is step 2 of the two-step flow.
 
        **Process:**
        1. Validates group is still open and not expired
        2. Confirms buyer's address is within delivery radius
        3. Links confirmed payment intent to commitment
        4. Creates group commitment record
        5. Updates group progress
        6. Checks if group target is reached (triggers fulfillment)
 
        **Two Payment Options:**
 
        **Option A: Pre-confirmed payment (recommended)**
        1. Call /create_payment_intent/ to get client_secret
        2. Confirm payment on frontend with Stripe.js
        3. Call this endpoint with confirmed payment_intent_id
 
        **Option B: Legacy flow**
        - Payment intent created automatically (less control)
 
        **Example Request:**
```json
        {
            "quantity": 5,
            "postcode": "E2 7DJ",
            "delivery_address_id": 12,
            "delivery_notes": "Ring doorbell",
            "payment_intent_id": "pi_xxx"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'quantity': {'type': 'integer', 'description': 'Quantity to purchase'},
                    'postcode': {'type': 'string', 'description': 'Delivery postcode'},
                    'delivery_address_id': {'type': 'integer', 'description': 'Delivery address ID'},
                    'delivery_notes': {'type': 'string', 'description': 'Optional delivery instructions'},
                    'payment_intent_id': {'type': 'string', 'description': 'Pre-confirmed Stripe payment intent ID'}
                },
                'required': ['quantity', 'postcode', 'delivery_address_id']
            }
        },
        responses={
            201: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'commitment': {'type': 'object'},
                    'payment_intent': {'type': 'object'},
                    'group_progress': {'type': 'number'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def commit(self, request, pk=None):
        """
        Commit to a buying group.
        This is step 2 of the two-step payment flow (after payment intent is confirmed).
        POST /api/buying-groups/{id}/commit/

        Body:
        {
            "quantity": 5,
            "postcode": "E2 7DJ",
            "delivery_address_id": 12,
            "delivery_notes": "Ring doorbell",
            "payment_intent_id": "pi_xxx"  // Optional: pre-confirmed payment intent
        }
        """
        group = self.get_object()

        quantity = request.data.get('quantity')
        buyer_postcode = request.data.get('postcode')
        delivery_address_id = request.data.get('delivery_address_id')
        delivery_notes = request.data.get('delivery_notes')
        payment_intent_id = request.data.get(
            'payment_intent_id')  # New: optional confirmed payment

        if not all([quantity, buyer_postcode, delivery_address_id]):
            return Response({
                'error': 'quantity, postcode, and delivery_address_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.commit_to_group(
            group_id=group.id,
            buyer=request.user,
            quantity=int(quantity),
            buyer_postcode=buyer_postcode,
            delivery_address_id=int(delivery_address_id),
            delivery_notes=delivery_notes,
            # Pass the confirmed payment intent if provided
            payment_intent_id=payment_intent_id
        )

        if result.success:
            # Handle both dict and object return types from service
            if isinstance(result.data, dict):
                commitment = result.data.get('commitment')
                payment_intent = result.data.get('payment_intent')
                progress_percent = result.data.get('progress_percent')
            else:
                # If service returns the commitment object directly
                commitment = result.data
                payment_intent = None
                # Refresh group to get updated progress
                group.refresh_from_db()
                progress_percent = group.progress_percent

            return Response({
                'message': 'Successfully committed to group',
                'commitment': GroupCommitmentSerializer(commitment).data,
                'payment_intent': payment_intent,
                'group_progress': progress_percent
            }, status=status.HTTP_201_CREATED)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Validate if address is within group delivery radius",
        description="""
        Check if a delivery address is within the buying group's geographic coverage.
 
        **Process:**
        1. Retrieves the address from user's address book
        2. Geocodes the address postcode
        3. Calculates distance from group center point
        4. Returns validation result and exact distance
 
        **Use Cases:**
        - Pre-validation before commitment
        - Show delivery eligibility on group details page
        - Frontend address selection validation
 
        **Example Request:**
```json
        {
            "address_id": 123
        }
```
 
        **Example Response:**
```json
        {
            "valid": true,
            "distance_km": 3.45,
            "max_distance_km": 5,
            "message": "Address is valid"
        }
```
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'address_id': {'type': 'integer', 'description': 'User address ID to validate'}
                },
                'required': ['address_id']
            }
        },
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'valid': {'type': 'boolean'},
                    'distance_km': {'type': 'number'},
                    'max_distance_km': {'type': 'number'},
                    'message': {'type': 'string'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def validate_address(self, request, pk=None):
        """
        Validate if an address is within the group's radius.
        POST /api/buying-groups/{id}/validate_address/
        Body: { "address_id": 123 }
        """
        group = self.get_object()
        address_id = request.data.get('address_id')

        if not address_id:
            return Response({
                'error': 'address_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get the address
        try:
            address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            return Response({
                'error': 'Address not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Geocode the address postcode
        from apps.integrations.services.geocoding_service import GeocodingService

        geo_service = GeocodingService()
        location_result = geo_service.geocode_postcode(address.postcode)

        if not location_result.success:
            return Response({
                'error': 'Could not validate address location',
                'valid': False
            }, status=status.HTTP_200_OK)

        # Check distance
        address_location = location_result.data['point']

        logger.info(
            f"Validating address {address_id} (postcode: {address.postcode})")
        logger.info(f"Group center_point: {group.center_point}")
        logger.info(f"Address location: {address_location}")
        logger.info(f"Group center_point type: {type(group.center_point)}")
        logger.info(f"Address location type: {type(address_location)}")

        if group.center_point is None:
            logger.error(f"Group {group.id} has no center_point!")
            return Response({
                'error': 'Group has no center point configured',
                'valid': False
            }, status=status.HTTP_200_OK)

        # Use proper geodesic distance calculation (haversine formula)
        distance_km = float(geo_service.calculate_distance(
            group.center_point, address_location))

        logger.info(f"Calculated distance: {distance_km}km")

        is_valid = distance_km <= group.radius_km

        return Response({
            'valid': is_valid,
            'distance_km': round(distance_km, 2),
            'max_distance_km': group.radius_km,
            'message': f'Address is {distance_km:.1f}km from group center' if not is_valid else 'Address is valid'
        })

    @extend_schema(
        summary="Cancel a commitment to a buying group",
        description="""
        Cancel your active commitment and receive a refund.
 
        **Process:**
        1. Finds user's active commitment to this group
        2. Validates commitment can be cancelled (group still open)
        3. Processes refund via Stripe
        4. Updates group progress
        5. Sends cancellation confirmation
 
        **Refund Policy:**
        - Full refund if group hasn't reached target
        - Partial refund may apply if group is being fulfilled
        - No refund after products are shipped
 
        **Use Cases:**
        - Buyer changed mind
        - Found better deal elsewhere
        - Delivery address changed
 
        **Permissions:** Authenticated users only (must own the commitment)
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'},
                    'refund_status': {'type': 'string'},
                    'refund_amount': {'type': 'number'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel_commitment(self, request, pk=None):
        """
        Cancel a commitment to a buying group.
        POST /api/buying-groups/{id}/cancel_commitment/
        """
        group = self.get_object()

        # Find user's commitment
        commitment = GroupCommitment.objects.filter(
            group=group,
            buyer=request.user,
            status='pending'
        ).first()

        if not commitment:
            return Response({
                'error': 'No active commitment found'
            }, status=status.HTTP_404_NOT_FOUND)

        result = self.service.cancel_commitment(
            commitment_id=commitment.id,
            buyer=request.user
        )

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        summary="Get all active buying groups",
        description="""
        Retrieve all currently active (open and non-expired) buying groups.
 
        **Filters:**
        - Only shows groups with status='open'
        - Only shows groups not yet expired
        - Ordered by creation date (newest first)
 
        **Use Cases:**
        - Homepage featured groups
        - Browse active opportunities
        - Group discovery
 
        **Permissions:** Public (no authentication required)
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'groups': {'type': 'array'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=False, methods=['get'])
    def active_groups(self, request):
        """
        Get all active buying groups.
        GET /api/buying-groups/active_groups/
        """
        groups = self.get_queryset().filter(
            status='open',
            expires_at__gt=timezone.now()
        )

        serializer = self.get_serializer(groups, many=True)
        return Response({
            'count': groups.count(),
            'groups': serializer.data
        })

    @extend_schema(
        summary="Find buying groups near a location",
        description="""
        Search for buying groups that deliver to a specific postcode within a radius.
 
        **Search Process:**
        1. Geocodes the provided postcode
        2. Finds groups within specified radius
        3. Only returns open, non-expired groups
        4. Ordered by distance (closest first)
 
        **Query Parameters:**
        - `postcode` (required): UK postcode to search from
        - `radius` (optional): Search radius in km (default: 10)
 
        **Example Request:**
```
        GET /api/buying-groups/near_me/?postcode=E27DJ&radius=5
```
 
        **Use Cases:**
        - Location-based group discovery
        - Find local buying opportunities
        - Check delivery availability
 
        **Permissions:** Public (no authentication required)
        """,
        parameters=[
            OpenApiParameter(
                name='postcode',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description='UK postcode to search from'
            ),
            OpenApiParameter(
                name='radius',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Search radius in kilometers (default: 10)'
            ),
        ],
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'count': {'type': 'integer'},
                    'location': {'type': 'string'},
                    'radius_km': {'type': 'integer'},
                    'groups': {'type': 'array'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def near_me(self, request):
        """
        Get buying groups near a location.
        GET /api/buying-groups/near_me/?postcode=SW1A1AA&radius=10
        """
        postcode = request.query_params.get('postcode')
        radius_km = int(request.query_params.get('radius', 10))

        if not postcode:
            return Response({
                'error': 'postcode parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Use geocoding service to get coordinates
        from apps.integrations.services.geocoding_service import GeocodingService
        geo_service = GeocodingService()

        location_result = geo_service.geocode_postcode(postcode)

        if not location_result.success:
            return Response({
                'error': 'Invalid postcode'
            }, status=status.HTTP_400_BAD_REQUEST)

        point = location_result.data['point']

        # Find groups within radius
        from django.contrib.gis.measure import D
        groups = BuyingGroup.objects.filter(
            status='open',
            expires_at__gt=timezone.now(),
            center_point__distance_lte=(point, D(km=radius_km))
        ).select_related('product__vendor')

        serializer = BuyingGroupListSerializer(groups, many=True)
        return Response({
            'count': groups.count(),
            'location': postcode,
            'radius_km': radius_km,
            'groups': serializer.data
        })

    @extend_schema(
        summary="Get real-time group status",
        description="""
        Retrieve real-time status and recent updates for WebSocket initialization.
 
        **Includes:**
        - Current group progress and participants count
        - Remaining time until expiration
        - Recent group updates (last 10 events)
        - Commitment activity feed
        - Progress milestones
 
        **Use Cases:**
        - Initialize WebSocket connection
        - Display live progress bar
        - Show recent activity feed
        - Real-time group monitoring
 
        **Permissions:** Public (no authentication required)
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'group': {'type': 'object'},
                    'recent_updates': {'type': 'array'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=True, methods=['get'])
    def realtime_status(self, request, pk=None):
        """
        Get real-time status of a group for WebSocket initialization.
        GET /api/buying-groups/{id}/realtime_status/
        """
        group = self.get_object()

        serializer = BuyingGroupRealtimeSerializer(group)

        # Get recent updates
        recent_updates = GroupUpdate.objects.filter(
            group=group
        ).order_by('-created_at')[:10]

        return Response({
            'group': serializer.data,
            'recent_updates': [
                {
                    'type': update.event_type,
                    'data': update.event_data,
                    'created_at': update.created_at
                }
                for update in recent_updates
            ]
        })

    @extend_schema(
        summary="Get user's buying group commitments",
        description="""
        Retrieve all buying group commitments for the authenticated user.
 
        **Organized by Status:**
        - **Active:** Pending commitments in open groups
        - **Confirmed:** Commitments in groups that reached target and are being fulfilled
        - **Cancelled:** User-cancelled commitments with refunds
 
        **Includes:**
        - Full group and product details
        - Payment status and amount
        - Delivery address and notes
        - Commitment date and status history
 
        **Use Cases:**
        - User dashboard
        - Order history
        - Track active group participations
        - View refund status
 
        **Permissions:** Authenticated users only
        """,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'active': {'type': 'array'},
                    'confirmed': {'type': 'array'},
                    'cancelled': {'type': 'array'},
                    'total_count': {'type': 'integer'}
                }
            }
        },
        tags=['Buying Groups']
    )
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_commitments(self, request):
        """
        Get current user's group commitments.
        GET /api/buying-groups/my_commitments/
        """
        commitments = GroupCommitment.objects.filter(
            buyer=request.user
        ).select_related(
            'group__product__vendor',
            'group__product__category'
        ).order_by('-committed_at')

        # Separate by status
        active = commitments.filter(status='pending')
        confirmed = commitments.filter(status='confirmed')
        cancelled = commitments.filter(status='cancelled')

        return Response({
            'active': GroupCommitmentSerializer(active, many=True).data,
            'confirmed': GroupCommitmentSerializer(confirmed, many=True).data,
            'cancelled': GroupCommitmentSerializer(cancelled, many=True).data,
            'total_count': commitments.count(),
        })


@extend_schema_view(
    list=extend_schema(
        summary="List group commitments",
        description="""
        Retrieve group commitments with filtering.
 
        **Filtering:**
        - Users see only their own commitments (unless staff)
        - Filter by group ID
        - Filter by commitment status
 
        **Permissions:** Authenticated users only
        """,
        parameters=[
            OpenApiParameter(
                name='group',
                type=Types.INT,
                location=OpenApiParameter.QUERY,
                description='Filter by buying group ID'
            ),
            OpenApiParameter(
                name='status',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by status (pending, confirmed, cancelled)'
            ),
        ],
        tags=['Buying Groups']
    ),
    retrieve=extend_schema(
        summary="Get commitment details",
        description="""
        Retrieve detailed information about a specific commitment.
 
        **Permissions:** Commitment owner or admin only
        """,
        tags=['Buying Groups']
    ),
)
class GroupCommitmentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing group commitments.
    Read-only access to commitment history.
    """
    queryset = GroupCommitment.objects.all()
    serializer_class = GroupCommitmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter commitments by user or group."""
        queryset = super().get_queryset().select_related(
            'group__product', 'buyer'
        )

        # Filter by current user unless staff
        if not self.request.user.is_staff:
            queryset = queryset.filter(buyer=self.request.user)

        # Filter by group
        group_id = self.request.query_params.get('group')
        if group_id:
            queryset = queryset.filter(group_id=group_id)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by('-committed_at')
