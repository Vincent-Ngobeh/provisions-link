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
