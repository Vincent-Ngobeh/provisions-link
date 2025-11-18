"""
ViewSet implementations for integration operations.
Handles FSA verification, Stripe operations, and geocoding.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
import stripe
import json
import logging

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample
)
from drf_spectacular.types import OpenApiTypes as Types

from apps.vendors.models import Vendor
from apps.orders.models import Order
from apps.buying_groups.models import GroupCommitment
from .services.fsa_service import FSAService
from .services.geocoding_service import GeocodingService
from .services.stripe_service import StripeConnectService
from .services.stripe_webhook_handler import StripeWebhookHandler
from .serializers import (
    StripeAccountLinkSerializer,
    StripePaymentIntentSerializer,
    PaymentMethodSerializer
)

logger = logging.getLogger(__name__)


@extend_schema_view(
    search_establishment=extend_schema(
        summary="Search FSA establishments",
        description="""
        Search the Food Standards Agency (FSA) database for food establishments.
 
        **Use Cases:**
        - Verify vendor business registration with FSA
        - Find food hygiene ratings for establishments
        - Search by business name and postcode
 
        **Request Example:**
```json
        {
            "business_name": "The Golden Spoon",
            "postcode": "SW1A 1AA",
            "max_results": 5
        }
```
 
        **Response Example:**
```json
        {
            "establishments": [
                {
                    "fhrsid": "12345",
                    "business_name": "The Golden Spoon",
                    "rating_value": "5",
                    "rating_date": "2024-01-15",
                    "postcode": "SW1A 1AA",
                    "address": "123 High Street, London"
                }
            ]
        }
```
 
        **FSA Rating Scale:**
        - 5: Very good hygiene
        - 4: Good hygiene
        - 3: Generally satisfactory hygiene
        - 2: Improvement necessary
        - 1: Major improvement necessary
        - 0: Urgent improvement required
 
        **Permissions:** Authenticated users only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'business_name': {'type': 'string', 'description': 'Name of the food business'},
                    'postcode': {'type': 'string', 'description': 'UK postcode (e.g., "SW1A 1AA")'},
                    'max_results': {'type': 'integer', 'description': 'Maximum number of results (default: 5)', 'default': 5}
                },
                'required': ['business_name', 'postcode']
            }
        },
        responses={
            200: {
                'description': 'Search results',
                'examples': [
                    OpenApiExample(
                        'Success Response',
                        value={
                            'establishments': [
                                {
                                    'fhrsid': '12345',
                                    'business_name': 'The Golden Spoon',
                                    'rating_value': '5',
                                    'rating_date': '2024-01-15',
                                    'postcode': 'SW1A 1AA'
                                }
                            ]
                        }
                    )
                ]
            },
            400: {'description': 'Invalid request or FSA API error'}
        },
        tags=['FSA Integration']
    ),
    verify_vendor=extend_schema(
        summary="Verify vendor's FSA rating",
        description="""
        Verify and update a vendor's Food Standards Agency (FSA) hygiene rating.
 
        **Process:**
        1. Validates vendor ownership (vendor owner or staff only)
        2. Fetches latest rating from FSA API
        3. Updates vendor record with rating and verification date
        4. Caches result to avoid excessive API calls
 
        **Force Update:**
        Set `force=true` to bypass cache and fetch fresh data from FSA.
 
        **Request Example:**
```json
        {
            "vendor_id": 5,
            "force": false
        }
```
 
        **Response Example:**
```json
        {
            "message": "FSA verification completed",
            "rating": {
                "rating_value": "5",
                "rating_date": "2024-01-15",
                "fhrsid": "12345",
                "verified_at": "2024-02-20T10:30:00Z"
            }
        }
```
 
        **Error Codes:**
        - `VENDOR_NOT_FOUND`: Vendor ID doesn't exist
        - `PERMISSION_DENIED`: User doesn't own vendor
        - `FSA_NOT_FOUND`: Business not found in FSA database
        - `FSA_API_ERROR`: FSA service unavailable
 
        **Permissions:** Vendor owner or staff only
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'vendor_id': {'type': 'integer', 'description': 'Vendor ID to verify'},
                    'force': {'type': 'boolean', 'description': 'Force fresh fetch from FSA (bypass cache)', 'default': False}
                },
                'required': ['vendor_id']
            }
        },
        responses={
            200: {
                'description': 'Verification completed',
                'examples': [
                    OpenApiExample(
                        'Successful Verification',
                        value={
                            'message': 'FSA verification completed',
                            'rating': {
                                'rating_value': '5',
                                'rating_date': '2024-01-15',
                                'verified_at': '2024-02-20T10:30:00Z'
                            }
                        }
                    )
                ]
            },
            400: {'description': 'Invalid request or FSA verification failed'},
            403: {'description': 'Permission denied - not vendor owner'},
            404: {'description': 'Vendor not found'}
        },
        tags=['FSA Integration']
    ),
    rating_distribution=extend_schema(
        summary="Get FSA rating distribution for area",
        description="""
        Get the distribution of FSA hygiene ratings for a specific postcode area.
 
        **Use Cases:**
        - Market analysis for new vendor onboarding
        - Display area quality metrics to buyers
        - Competitive analysis for vendors
 
        **Postcode Areas:**
        - Use partial postcode (e.g., "SW1", "E1", "M1")
        - Returns aggregate statistics for that area
 
        **Response Example:**
```json
        {
            "postcode_area": "SW1",
            "total_establishments": 234,
            "distribution": {
                "5": 120,
                "4": 65,
                "3": 30,
                "2": 12,
                "1": 5,
                "0": 2
            },
            "average_rating": 4.2,
            "percentage_4_or_above": 79.1
        }
```
 
        **Permissions:** Public (AllowAny) - no authentication required
        """,
        parameters=[
            OpenApiParameter(
                name='postcode_area',
                type=Types.STR,
                location=OpenApiParameter.QUERY,
                description='UK postcode area (e.g., "SW1", "E1", "M1")',
                required=True,
                examples=[
                    OpenApiExample('London Westminster', value='SW1'),
                    OpenApiExample('East London', value='E1'),
                    OpenApiExample('Manchester', value='M1'),
                ]
            ),
        ],
        responses={
            200: {
                'description': 'Rating distribution statistics',
                'examples': [
                    OpenApiExample(
                        'Distribution Response',
                        value={
                            'postcode_area': 'SW1',
                            'total_establishments': 234,
                            'distribution': {
                                '5': 120,
                                '4': 65,
                                '3': 30
                            },
                            'average_rating': 4.2
                        }
                    )
                ]
            },
            400: {'description': 'Invalid postcode area or FSA API error'}
        },
        tags=['FSA Integration']
    )
)
class FSAIntegrationViewSet(viewsets.ViewSet):
    """
    ViewSet for FSA (Food Standards Agency) operations.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def search_establishment(self, request):
        """
        Search FSA establishments.
        POST /api/integrations/fsa/search_establishment/
        """
        business_name = request.data.get('business_name')
        postcode = request.data.get('postcode')

        if not all([business_name, postcode]):
            return Response({
                'error': 'business_name and postcode are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = FSAService()
        result = service.search_establishment(
            business_name=business_name,
            postcode=postcode,
            max_results=request.data.get('max_results', 5)
        )

        if result.success:
            return Response({
                'establishments': result.data
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def verify_vendor(self, request):
        """
        Verify vendor's FSA rating.
        POST /api/integrations/fsa/verify_vendor/
        """
        vendor_id = request.data.get('vendor_id')

        if not vendor_id:
            return Response({
                'error': 'vendor_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check permission
        try:
            vendor = Vendor.objects.get(id=vendor_id)
            if vendor.user != request.user and not request.user.is_staff:
                return Response({
                    'error': 'Permission denied'
                }, status=status.HTTP_403_FORBIDDEN)
        except Vendor.DoesNotExist:
            return Response({
                'error': 'Vendor not found'
            }, status=status.HTTP_404_NOT_FOUND)

        service = FSAService()
        result = service.update_vendor_rating(
            vendor_id=vendor_id,
            force=request.data.get('force', False)
        )

        if result.success:
            return Response({
                'message': 'FSA verification completed',
                'rating': result.data
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def rating_distribution(self, request):
        """
        Get FSA rating distribution for an area.
        GET /api/integrations/fsa/rating_distribution/?postcode_area=SW1
        """
        postcode_area = request.query_params.get('postcode_area')

        if not postcode_area:
            return Response({
                'error': 'postcode_area parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = FSAService()
        result = service.get_rating_distribution(postcode_area)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    geocode_postcode=extend_schema(
        summary="Geocode a UK postcode",
        description="""
        Convert a UK postcode to geographic coordinates (latitude/longitude).
 
        **Use Cases:**
        - Calculate delivery distances
        - Display vendor locations on maps
        - Find nearby vendors for buyers
        - Validate address information
 
        **Data Source:**
        Uses Postcodes.io API (free, no API key required)
 
        **Request Example:**
```json
        {
            "postcode": "SW1A 1AA"
        }
```
 
        **Response Example:**
```json
        {
            "postcode": "SW1A 1AA",
            "location": {
                "lat": 51.501009,
                "lng": -0.141588
            },
            "area_name": "Westminster",
            "confidence": 100
        }
```
 
        **Error Handling:**
        - Returns 400 if postcode not found
        - Handles partial postcodes (e.g., "SW1A")
        - Case-insensitive matching
 
        **Permissions:** Public (no authentication required)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'postcode': {'type': 'string', 'description': 'UK postcode (e.g., "SW1A 1AA", "E1 6AN")'}
                },
                'required': ['postcode']
            }
        },
        responses={
            200: {
                'description': 'Geocoding successful',
                'examples': [
                    OpenApiExample(
                        'Buckingham Palace',
                        value={
                            'postcode': 'SW1A 1AA',
                            'location': {'lat': 51.501009, 'lng': -0.141588},
                            'area_name': 'Westminster',
                            'confidence': 100
                        }
                    ),
                    OpenApiExample(
                        'Tower of London',
                        value={
                            'postcode': 'EC3N 4AB',
                            'location': {'lat': 51.508112, 'lng': -0.075949},
                            'area_name': 'Tower Hamlets',
                            'confidence': 100
                        }
                    )
                ]
            },
            400: {'description': 'Invalid postcode or not found'}
        },
        tags=['Geocoding']
    ),
    geocode_address=extend_schema(
        summary="Geocode a full address",
        description="""
        Convert a full UK address to geographic coordinates.
 
        **Use Cases:**
        - Vendor registration with full address
        - Delivery address validation
        - Distance calculations for complex addresses
 
        **Address Formats:**
        - Full address string: "123 High Street, London, SW1A 1AA"
        - Separate address and postcode fields for better accuracy
 
        **Request Example:**
```json
        {
            "address": "123 High Street, London",
            "postcode": "SW1A 1AA"
        }
```
 
        **Response Example:**
```json
        {
            "address": "123 High Street, London",
            "location": {
                "lat": 51.501009,
                "lng": -0.141588
            },
            "formatted_address": "123 High Street, Westminster, London SW1A 1AA",
            "confidence": 95
        }
```
 
        **Confidence Scores:**
        - 100: Exact postcode match
        - 90-99: Address-level match
        - 80-89: Street-level match
        - <80: Area-level match (less precise)
 
        **Permissions:** Public (no authentication required)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'address': {'type': 'string', 'description': 'Full address or street address'},
                    'postcode': {'type': 'string', 'description': 'UK postcode (optional, improves accuracy)'}
                },
                'required': ['address']
            }
        },
        responses={
            200: {
                'description': 'Address geocoded successfully',
                'examples': [
                    OpenApiExample(
                        'Full Address',
                        value={
                            'address': '10 Downing Street, London',
                            'postcode': 'SW1A 2AA',
                            'location': {'lat': 51.503396, 'lng': -0.127764},
                            'confidence': 95
                        }
                    )
                ]
            },
            400: {'description': 'Invalid address or geocoding failed'}
        },
        tags=['Geocoding']
    ),
    calculate_distance=extend_schema(
        summary="Calculate distance between two points",
        description="""
        Calculate the distance between two geographic coordinates.
 
        **Use Cases:**
        - Calculate delivery distance from vendor to buyer
        - Filter vendors by distance from buyer location
        - Display "X miles away" on vendor listings
        - Delivery fee calculations
 
        **Distance Calculation:**
        - Uses Haversine formula for accurate spherical distance
        - Returns both kilometers and miles
        - Considers Earth's curvature
 
        **Request Example:**
```json
        {
            "point1": {"lat": 51.501009, "lng": -0.141588},
            "point2": {"lat": 51.508112, "lng": -0.075949}
        }
```
 
        **Response Example:**
```json
        {
            "distance_km": 5.47,
            "distance_miles": 3.40
        }
```
 
        **Point Format:**
        Each point must have:
        - `lat`: Latitude (-90 to 90)
        - `lng`: Longitude (-180 to 180)
 
        **Permissions:** Public (no authentication required)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'point1': {
                        'type': 'object',
                        'description': 'First location',
                        'properties': {
                            'lat': {'type': 'number', 'format': 'float'},
                            'lng': {'type': 'number', 'format': 'float'}
                        },
                        'required': ['lat', 'lng']
                    },
                    'point2': {
                        'type': 'object',
                        'description': 'Second location',
                        'properties': {
                            'lat': {'type': 'number', 'format': 'float'},
                            'lng': {'type': 'number', 'format': 'float'}
                        },
                        'required': ['lat', 'lng']
                    }
                },
                'required': ['point1', 'point2']
            }
        },
        responses={
            200: {
                'description': 'Distance calculated successfully',
                'examples': [
                    OpenApiExample(
                        'Buckingham Palace to Tower of London',
                        value={
                            'distance_km': 5.47,
                            'distance_miles': 3.40
                        }
                    )
                ]
            },
            400: {'description': 'Invalid point format'}
        },
        tags=['Geocoding']
    )
)
class GeocodingViewSet(viewsets.ViewSet):
    """
    ViewSet for geocoding operations.
    """
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def geocode_postcode(self, request):
        """
        Geocode a UK postcode.
        POST /api/integrations/geocoding/geocode_postcode/
        """
        postcode = request.data.get('postcode')

        if not postcode:
            return Response({
                'error': 'postcode is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = GeocodingService()
        result = service.geocode_postcode(postcode)

        if result.success:
            return Response({
                'postcode': postcode,
                'location': {
                    'lat': result.data['lat'],
                    'lng': result.data['lng']
                },
                'area_name': result.data.get('area_name'),
                'confidence': result.data.get('confidence')
            })

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def geocode_address(self, request):
        """
        Geocode a full address.
        POST /api/integrations/geocoding/geocode_address/
        """
        address = request.data.get('address')
        postcode = request.data.get('postcode')

        if not address:
            return Response({
                'error': 'address is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = GeocodingService()
        result = service.geocode_address(address, postcode)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def calculate_distance(self, request):
        """
        Calculate distance between two points.
        POST /api/integrations/geocoding/calculate_distance/
        """
        from django.contrib.gis.geos import Point

        point1_data = request.data.get('point1')
        point2_data = request.data.get('point2')

        if not all([point1_data, point2_data]):
            return Response({
                'error': 'point1 and point2 are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            point1 = Point(point1_data['lng'], point1_data['lat'])
            point2 = Point(point2_data['lng'], point2_data['lat'])
        except (KeyError, TypeError):
            return Response({
                'error': 'Invalid point format. Expected {lng, lat}'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = GeocodingService()
        distance = service.calculate_distance(point1, point2)

        return Response({
            'distance_km': float(distance),
            'distance_miles': float(distance * 0.621371)
        })


@extend_schema_view(
    create_payment_intent=extend_schema(
        summary="[DEPRECATED] Create Stripe payment intent",
        description="""
        **⚠️ DEPRECATED:** This endpoint is deprecated. Use `/api/v1/payments/create-intent/` instead.
 
        Kept for backward compatibility only. Will be removed in future versions.
 
        Create a payment intent for an order or group commitment using Stripe Connect.
 
        **Migration Guide:**
        - Old endpoint: `POST /api/integrations/stripe/create_payment_intent/`
        - New endpoint: `POST /api/v1/payments/create-intent/`
        - The new endpoint has improved error handling and commission calculations
 
        **Request Example:**
```json
        {
            "order_id": 45
        }
```
        or
```json
        {
            "group_commitment_id": 12
        }
```
 
        **Response Example:**
```json
        {
            "payment_intent_id": "pi_xxx",
            "client_secret": "pi_xxx_secret_yyy",
            "amount": 15000,
            "commission": 500
        }
```
 
        **Permissions:** Authenticated users (order buyer or commitment member)
        """,
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'order_id': {'type': 'integer', 'description': 'Order ID to create payment for'},
                    'group_commitment_id': {'type': 'integer', 'description': 'Group commitment ID to create payment for'}
                }
            }
        },
        responses={
            200: {'description': 'Payment intent created'},
            400: {'description': 'Invalid request or Stripe error'},
            404: {'description': 'Order or commitment not found'}
        },
        tags=['Stripe Integration (Deprecated)'],
        deprecated=True
    ),
    account_status=extend_schema(
        summary="Check vendor's Stripe Connect account status",
        description="""
        Check the status of a vendor's Stripe Connect account.
 
        **Use Cases:**
        - Verify vendor can receive payments
        - Check if onboarding is complete
        - Display account status to vendor
 
        **Account Statuses:**
        - `complete`: Account fully set up and can receive payments
        - `pending`: Onboarding started but not complete
        - `restricted`: Account has restrictions (verification needed)
        - `disabled`: Account disabled by Stripe or platform
        - `not_connected`: No Stripe account linked
 
        **Response Example:**
```json
        {
            "account_id": "acct_xxxxx",
            "status": "complete",
            "charges_enabled": true,
            "payouts_enabled": true,
            "details_submitted": true,
            "requirements": {
                "currently_due": [],
                "eventually_due": [],
                "pending_verification": []
            },
            "capabilities": {
                "card_payments": "active",
                "transfers": "active"
            }
        }
```
 
        **Requirements:**
        - `currently_due`: Information needed now to continue receiving payments
        - `eventually_due`: Information needed in the future
        - `pending_verification`: Documents under review by Stripe
 
        **Permissions:** Vendor owner only (must have vendor account)
        """,
        responses={
            200: {
                'description': 'Account status retrieved',
                'examples': [
                    OpenApiExample(
                        'Complete Account',
                        value={
                            'account_id': 'acct_xxxxx',
                            'status': 'complete',
                            'charges_enabled': True,
                            'payouts_enabled': True,
                            'details_submitted': True
                        }
                    ),
                    OpenApiExample(
                        'Pending Account',
                        value={
                            'account_id': 'acct_xxxxx',
                            'status': 'pending',
                            'charges_enabled': False,
                            'payouts_enabled': False,
                            'requirements': {
                                'currently_due': ['business_url', 'external_account']
                            }
                        }
                    )
                ]
            },
            400: {'description': 'Stripe API error'},
            403: {'description': 'Vendor account required'}
        },
        tags=['Stripe Integration']
    ),
    balance=extend_schema(
        summary="Get vendor's Stripe balance",
        description="""
        Retrieve the current balance for a vendor's Stripe Connect account.
 
        **Use Cases:**
        - Display available balance to vendor
        - Show pending balance awaiting payout
        - Track earnings and payouts
 
        **Balance Types:**
        - `available`: Funds available for immediate payout
        - `pending`: Funds waiting to become available (typically 2-7 days)
        - `connect_reserved`: Funds held in reserve by platform
 
        **Response Example:**
```json
        {
            "available": [
                {
                    "amount": 45000,
                    "currency": "gbp",
                    "source_types": {
                        "card": 45000
                    }
                }
            ],
            "pending": [
                {
                    "amount": 12000,
                    "currency": "gbp",
                    "source_types": {
                        "card": 12000
                    }
                }
            ],
            "total_available_gbp": 450.00,
            "total_pending_gbp": 120.00
        }
```
 
        **Important Notes:**
        - Amounts are in pence (divide by 100 for pounds)
        - Balance updated in real-time from Stripe
        - Payout schedule configured per vendor (daily, weekly, monthly)
 
        **Payout Schedule:**
        - **Daily**: Automatic payouts every business day
        - **Weekly**: Payouts every Monday
        - **Monthly**: Payouts on 1st of each month
        - Funds from a payment typically available 2-7 days after capture
 
        **Permissions:** Vendor owner only (must have vendor account)
        """,
        responses={
            200: {
                'description': 'Balance retrieved successfully',
                'examples': [
                    OpenApiExample(
                        'Balance with Available and Pending',
                        value={
                            'available': [
                                {
                                    'amount': 45000,
                                    'currency': 'gbp'
                                }
                            ],
                            'pending': [
                                {
                                    'amount': 12000,
                                    'currency': 'gbp'
                                }
                            ],
                            'total_available_gbp': 450.00,
                            'total_pending_gbp': 120.00
                        }
                    )
                ]
            },
            400: {'description': 'Stripe API error'},
            403: {'description': 'Vendor account required'}
        },
        tags=['Stripe Integration']
    )
)
class StripeIntegrationViewSet(viewsets.ViewSet):
    """
    ViewSet for Stripe operations.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def create_payment_intent(self, request):
        """
        Create a payment intent for an order or group commitment.
        POST /api/integrations/stripe/create_payment_intent/

        NOTE: This endpoint is deprecated. Use /api/v1/payments/create-intent/ instead.
        Kept for backward compatibility.
        """
        order_id = request.data.get('order_id')
        group_commitment_id = request.data.get('group_commitment_id')

        if not order_id and not group_commitment_id:
            return Response({
                'error': 'Either order_id or group_commitment_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        service = StripeConnectService()

        if order_id:
            try:
                order = Order.objects.get(id=order_id, buyer=request.user)
                result = service.process_marketplace_order(order)
            except Order.DoesNotExist:
                return Response({
                    'error': 'Order not found'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            try:
                commitment = GroupCommitment.objects.get(
                    id=group_commitment_id,
                    buyer=request.user
                )
                from apps.buying_groups.services.group_buying_service import GroupBuyingService
                group_service = GroupBuyingService()
                amount = group_service.calculate_commitment_amount(
                    commitment.group,
                    commitment.quantity
                )
                result = service.create_payment_intent_for_group(
                    amount=amount,
                    group_id=commitment.group.id,
                    buyer_id=request.user.id
                )
            except GroupCommitment.DoesNotExist:
                return Response({
                    'error': 'Commitment not found'
                }, status=status.HTTP_404_NOT_FOUND)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def account_status(self, request):
        """
        Check Stripe Connect account status.
        GET /api/integrations/stripe/account_status/
        """
        if not hasattr(request.user, 'vendor'):
            return Response({
                'error': 'Vendor account required'
            }, status=status.HTTP_403_FORBIDDEN)

        service = StripeConnectService()
        result = service.check_account_status(request.user.vendor)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def balance(self, request):
        """
        Get vendor's Stripe balance.
        GET /api/integrations/stripe/balance/
        """
        if not hasattr(request.user, 'vendor'):
            return Response({
                'error': 'Vendor account required'
            }, status=status.HTTP_403_FORBIDDEN)

        service = StripeConnectService()
        result = service.get_vendor_balance(request.user.vendor)

        if result.success:
            return Response(result.data)

        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Stripe webhook handler",
    description="""
    **System-to-System Endpoint** - Called by Stripe, not by clients.
 
    Processes webhook events from Stripe for real-time payment and account updates.
 
    **Supported Events:**
    - `payment_intent.succeeded`: Payment completed successfully
    - `payment_intent.payment_failed`: Payment failed
    - `account.updated`: Vendor's Stripe account status changed
    - `payout.paid`: Funds transferred to vendor's bank account
    - `charge.refunded`: Refund processed
 
    **Security:**
    - Verifies Stripe webhook signature using signing secret
    - Rejects requests with invalid or missing signatures
    - Always returns 200 to prevent retry loops (even on processing errors)
 
    **Webhook Configuration:**
    Configure this endpoint in Stripe Dashboard:
    - URL: `https://yourdomain.com/webhooks/stripe/`
    - API version: Latest
    - Events: payment_intent.*, account.updated, payout.paid, charge.refunded
 
    **Response Behavior:**
    - Always returns 200 (even on processing errors) to acknowledge receipt
    - Only returns 400 for signature verification failures
    - Errors logged internally for debugging
 
    **Important Notes:**
    - This endpoint is called by Stripe servers, not by your frontend
    - Idempotent - safe to receive same event multiple times
    - Events processed asynchronously
    - Do not call this endpoint manually
 
    **Permissions:** Public (AllowAny) - authentication via Stripe signature
    """,
    request={
        'application/json': {
            'type': 'object',
            'description': 'Stripe webhook event payload (signed by Stripe)'
        }
    },
    responses={
        200: {
            'description': 'Event acknowledged and queued for processing',
            'examples': [
                OpenApiExample(
                    'Event Received',
                    value={
                        'received': True,
                        'event_id': 'evt_xxxxx',
                        'event_type': 'payment_intent.succeeded'
                    }
                )
            ]
        },
        400: {
            'description': 'Invalid signature or malformed payload',
            'examples': [
                OpenApiExample(
                    'Invalid Signature',
                    value={
                        'error': 'Invalid signature',
                        'error_code': 'INVALID_SIGNATURE'
                    }
                )
            ]
        }
    },
    tags=['Stripe Webhooks (System)'],
    exclude=False
)
@api_view(['POST'])
@csrf_exempt
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    Handle Stripe webhooks.
    POST /webhooks/stripe/

    This endpoint processes webhook events from Stripe for:
    - Payment confirmations (payment_intent.succeeded)
    - Payment failures (payment_intent.payment_failed)
    - Account updates (account.updated)
    - Payouts (payout.paid)
    - Refunds (charge.refunded)

    Security:
    - Verifies Stripe webhook signature
    - Always returns 200 to prevent retry loops
    - Logs all errors internally

    Returns:
        200: Event received (always, even on errors)
        400: Invalid signature or payload (only for security issues)
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    # Log webhook received
    logger.info(f"Stripe webhook received", extra={
        'content_length': len(payload),
        'has_signature': bool(sig_header)
    })

    # Verify signature
    if not sig_header:
        logger.error("Stripe webhook missing signature header")
        return JsonResponse({
            'error': 'Missing stripe signature'
        }, status=400)

    # Verify webhook signature using Stripe service
    stripe_service = StripeConnectService()
    verify_result = stripe_service.verify_webhook_signature(
        payload, sig_header)

    if not verify_result.success:
        logger.error(
            f"Stripe webhook signature verification failed: {verify_result.error}",
            extra={'error_code': verify_result.error_code}
        )
        return JsonResponse({
            'error': verify_result.error,
            'error_code': verify_result.error_code
        }, status=400)

    # Get verified event
    event = verify_result.data
    event_id = event.get('id')
    event_type = event.get('type')

    logger.info(f"Processing Stripe webhook: {event_type}", extra={
        'event_id': event_id,
        'event_type': event_type
    })

    # Delegate to webhook handler
    try:
        webhook_handler = StripeWebhookHandler()
        result = webhook_handler.handle_event(event)

        if result.success:
            logger.info(
                f"Successfully processed webhook: {event_type}",
                extra={
                    'event_id': event_id,
                    'result': result.data
                }
            )
        else:
            logger.error(
                f"Webhook handler failed: {result.error}",
                extra={
                    'event_id': event_id,
                    'event_type': event_type,
                    'error_code': result.error_code
                }
            )

    except Exception as e:
        # CRITICAL: Always return 200 even on errors
        # This prevents Stripe from retrying and creating loops
        logger.exception(
            f"Exception handling webhook {event_type}",
            extra={
                'event_id': event_id,
                'event_type': event_type
            }
        )

    # Always return 200 to acknowledge receipt
    return JsonResponse({
        'received': True,
        'event_id': event_id,
        'event_type': event_type
    }, status=200)
