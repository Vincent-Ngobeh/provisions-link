"""
ViewSet implementations for group buying operations.
Handles group creation, commitments, and real-time updates.
"""
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db.models import Q, F, Count
from django.utils import timezone

from .models import BuyingGroup, GroupCommitment, GroupUpdate
from .serializers import (
    BuyingGroupListSerializer,
    BuyingGroupDetailSerializer,
    BuyingGroupCreateSerializer,
    GroupCommitmentSerializer,
    BuyingGroupRealtimeSerializer
)
from .services.group_buying_service import GroupBuyingService


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
        """
        queryset = super().get_queryset().select_related(
            'product__vendor', 'product__category'
        ).annotate(
            participants_count=Count(
                'commitments', filter=Q(commitments__status='pending'))
        )

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

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

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def commit(self, request, pk=None):
        """
        Commit to a buying group.
        POST /api/buying-groups/{id}/commit/
        """
        group = self.get_object()

        quantity = request.data.get('quantity')
        buyer_postcode = request.data.get('postcode')

        if not all([quantity, buyer_postcode]):
            return Response({
                'error': 'quantity and postcode are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        result = self.service.commit_to_group(
            group_id=group.id,
            buyer=request.user,
            quantity=int(quantity),
            buyer_postcode=buyer_postcode
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
