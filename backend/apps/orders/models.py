# apps/orders/models.py

import uuid
from decimal import Decimal
from django.contrib.gis.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.core.models import User, Address
from apps.vendors.models import Vendor
from apps.products.models import Product
from apps.buying_groups.models import BuyingGroup


def generate_order_reference():
    """Generate unique order reference number."""
    year = timezone.now().year
    random_part = uuid.uuid4().hex[:6].upper()
    return f"PL-{year}-{random_part}"


class Order(models.Model):
    """
    Order model for B2B marketplace transactions.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]

    reference_number = models.CharField(
        max_length=20,
        unique=True,
        default=generate_order_reference,
        editable=False
    )

    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    delivery_address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    group = models.ForeignKey(
        BuyingGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        help_text="Associated buying group if applicable"
    )

    # Amounts
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    vat_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    delivery_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    marketplace_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Commission charged to vendor"
    )
    vendor_payout = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount to be paid to vendor after commission"
    )

    # Payment
    stripe_payment_intent_id = models.CharField(
        max_length=200,
        blank=True,
        help_text="Stripe payment intent ID"
    )

    # Delivery
    delivery_notes = models.TextField(
        blank=True,
        help_text="Special delivery instructions"
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'orders'
        verbose_name = _('Order')
        verbose_name_plural = _('Orders')
        indexes = [
            models.Index(fields=['reference_number']),
            models.Index(fields=['buyer', 'created_at']),
            models.Index(fields=['vendor', 'created_at']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['group']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.reference_number}"

    def calculate_totals(self):
        """Recalculate order totals based on items."""
        self.subtotal = sum(item.total_price for item in self.items.all())
        self.vat_amount = sum(item.vat_amount for item in self.items.all())
        self.total = self.subtotal + self.vat_amount + self.delivery_fee

        # Calculate marketplace fee and vendor payout
        if self.vendor.commission_rate:
            self.marketplace_fee = self.subtotal * self.vendor.commission_rate
            self.vendor_payout = self.total - self.marketplace_fee

        self.save()

    @property
    def is_paid(self):
        """Check if order has been paid."""
        return self.status in ['paid', 'processing', 'shipped', 'delivered']

    @property
    def can_cancel(self):
        """Check if order can be cancelled."""
        return self.status in ['pending', 'paid']


class OrderItem(models.Model):
    """
    Individual items within an order.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    quantity = models.IntegerField(
        validators=[MinValueValidator(1)]
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Price per unit at time of order"
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total price for this line item"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Discount applied (e.g., from group buy)"
    )

    class Meta:
        db_table = 'order_items'
        verbose_name = _('Order Item')
        verbose_name_plural = _('Order Items')
        indexes = [
            models.Index(fields=['order', 'product']),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"

    def save(self, *args, **kwargs):
        """Calculate total price before saving."""
        if not self.total_price:
            self.total_price = (
                self.unit_price * self.quantity) - self.discount_amount
        super().save(*args, **kwargs)

    @property
    def vat_amount(self):
        """Calculate VAT amount for this item."""
        return self.total_price * self.product.vat_rate
