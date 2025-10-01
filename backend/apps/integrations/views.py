"""
ViewSet implementations for integration operations.
Handles FSA verification, Stripe operations, and geocoding.
"""
from datetime import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
import stripe
import json

from apps.vendors.models import Vendor
from apps.orders.models import Order
from apps.buying_groups.models import GroupCommitment
from .services.fsa_service import FSAService
from .services.geocoding_service import GeocodingService
from .services.stripe_service import StripeConnectService
from .serializers import (
    StripeAccountLinkSerializer,
    StripePaymentIntentSerializer,
    PaymentMethodSerializer
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
    POST /api/integrations/webhooks/stripe/
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        return Response({
            'error': 'Missing stripe signature'
        }, status=status.HTTP_400_BAD_REQUEST)

    service = StripeConnectService()
    result = service.verify_webhook_signature(payload, sig_header)

    if not result.success:
        return Response({
            'error': result.error,
            'error_code': result.error_code
        }, status=status.HTTP_400_BAD_REQUEST)

    event = result.data

    # Handle different event types
    try:
        if event['type'] == 'payment_intent.succeeded':
            handle_payment_intent_succeeded(event['data']['object'])
        elif event['type'] == 'payment_intent.payment_failed':
            handle_payment_intent_failed(event['data']['object'])
        elif event['type'] == 'account.updated':
            handle_account_updated(event['data']['object'])
        elif event['type'] == 'payout.paid':
            handle_payout_paid(event['data']['object'])
    except Exception as e:
        # Log error but return 200 to prevent Stripe retries
        print(f"Webhook handler error: {e}")

    return Response({'received': True})


def handle_payment_intent_succeeded(payment_intent):
    """Handle successful payment."""
    order_id = payment_intent.get('metadata', {}).get('order_id')
    if order_id:
        try:
            order = Order.objects.get(id=order_id)
            order.status = 'paid'
            order.paid_at = timezone.now()
            order.save()
        except Order.DoesNotExist:
            pass


def handle_payment_intent_failed(payment_intent):
    """Handle failed payment."""
    # Log the failure
    print(f"Payment failed: {payment_intent.get('id')}")


def handle_account_updated(account):
    """Handle Stripe Connect account updates."""
    try:
        vendor = Vendor.objects.get(stripe_account_id=account['id'])
        vendor.stripe_onboarding_complete = account.get(
            'charges_enabled', False)
        vendor.save()
    except Vendor.DoesNotExist:
        pass


def handle_payout_paid(payout):
    """Handle successful vendor payout."""
    # Log the payout
    print(f"Payout completed: {payout.get('id')}")
