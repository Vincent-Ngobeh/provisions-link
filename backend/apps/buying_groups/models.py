# apps/buying_groups/models.py

from decimal import Decimal
from django.contrib.gis.db import models
from django.contrib.gis.measure import D
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import User
from apps.products.models import Product


class BuyingGroup(models.Model):
    """
    Location-based group buying for products.
    """
    STATUS_CHOICES = [
        ('open', 'Open for commitments'),
        ('active', 'Target reached - will process'),
        ('failed', 'Failed to reach minimum'),
        ('completed', 'Orders processed'),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='buying_groups'
    )

    # Location-based grouping
    center_point = models.PointField(
        geography=True,
        help_text="Center point of the buying group area"
    )
    radius_km = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Radius in kilometers"
    )
    area_name = models.CharField(
        max_length=100,
        help_text="Human-readable area name (e.g., 'Shoreditch area')"
    )

    # Group parameters
    target_quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Target quantity to achieve discount"
    )
    current_quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Current committed quantity"
    )
    min_quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Minimum quantity to activate group"
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(
            Decimal('0.00')), MaxValueValidator(Decimal('50.00'))],
        help_text="Discount percentage when target is reached"
    )

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_update_at = models.DateTimeField(auto_now=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='open'
    )

    class Meta:
        db_table = 'buying_groups'
        verbose_name = _('Buying Group')
        verbose_name_plural = _('Buying Groups')
        indexes = [
            models.Index(fields=['status', 'expires_at']),
            models.Index(fields=['product', 'status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.area_name} ({self.status})"

    @property
    def time_remaining(self):
        """Calculate time remaining until expiry."""
        if self.expires_at > timezone.now():
            return self.expires_at - timezone.now()
        return None

    @property
    def is_expired(self):
        """Check if the group has expired."""
        return self.expires_at <= timezone.now()

    @property
    def progress_percent(self):
        """Calculate progress towards target as percentage."""
        if self.target_quantity > 0:
            return min((self.current_quantity / self.target_quantity) * 100, 100)
        return 0

    @property
    def savings_per_unit(self):
        """Calculate savings per unit when discount is applied."""
        return self.product.price * (self.discount_percent / 100)

    @property
    def discounted_price(self):
        """Calculate the discounted price per unit."""
        return self.product.price * (1 - self.discount_percent / 100)

    def can_join(self, buyer_location):
        """Check if a buyer at the given location can join this group."""
        if self.status != 'open':
            return False
        if self.is_expired:
            return False
        if buyer_location:
            from math import radians, cos, sin, sqrt, atan2

            # Haversine formula for great circle distance
            lat1, lon1 = radians(self.center_point.y), radians(
                self.center_point.x)
            lat2, lon2 = radians(buyer_location.y), radians(buyer_location.x)

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance_km = 6371 * c  # Earth radius in km

            return distance_km <= self.radius_km
        return False

    def update_status(self):
        """Update group status based on current state."""
        if self.is_expired:
            if self.current_quantity >= self.min_quantity:
                self.status = 'active'
            else:
                self.status = 'failed'
        elif self.current_quantity >= self.target_quantity:
            self.status = 'active'
        self.save()


class GroupCommitment(models.Model):
    """
    Individual buyer commitments to a buying group.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    group = models.ForeignKey(
        BuyingGroup,
        on_delete=models.CASCADE,
        related_name='commitments'
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='group_commitments'
    )
    quantity = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantity committed to purchase"
    )

    # Location verification
    buyer_location = models.PointField(
        geography=True,
        help_text="Buyer's location at time of commitment"
    )
    buyer_postcode = models.CharField(
        max_length=10,
        help_text="Buyer's postcode"
    )

    # Payment
    stripe_payment_intent_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="Stripe payment intent for pre-authorization"
    )

    # Timestamps
    committed_at = models.DateTimeField(auto_now_add=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    class Meta:
        db_table = 'group_commitments'
        verbose_name = _('Group Commitment')
        verbose_name_plural = _('Group Commitments')
        # One commitment per buyer per group
        unique_together = [['group', 'buyer']]
        indexes = [
            models.Index(fields=['group', 'status']),
            models.Index(fields=['buyer', 'status']),
            models.Index(fields=['committed_at']),
        ]
        ordering = ['-committed_at']

    def __str__(self):
        return f"{self.buyer.email} - {self.quantity} units - {self.group.product.name}"

    @property
    def total_price(self):
        """Calculate total price with discount."""
        discount = self.group.discount_percent / 100
        return self.quantity * self.group.product.price * (1 - discount)

    @property
    def total_savings(self):
        """Calculate total savings from group discount."""
        return self.quantity * self.group.savings_per_unit


class GroupUpdate(models.Model):
    """
    WebSocket event tracking for real-time updates.
    """
    EVENT_TYPE_CHOICES = [
        ('commitment', 'New Commitment'),
        ('threshold', 'Threshold Reached'),
        ('expired', 'Group Expired'),
        ('cancelled', 'Commitment Cancelled'),
        ('status_change', 'Status Changed'),
    ]

    group = models.ForeignKey(
        BuyingGroup,
        on_delete=models.CASCADE,
        related_name='updates'
    )
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES
    )
    event_data = models.JSONField(
        default=dict,
        help_text="Additional event data"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'group_updates'
        verbose_name = _('Group Update')
        verbose_name_plural = _('Group Updates')
        indexes = [
            models.Index(fields=['group', 'created_at']),
            models.Index(fields=['event_type']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.group.product.name} - {self.event_type} - {self.created_at}"
