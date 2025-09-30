# apps/vendors/models.py

from decimal import Decimal
from django.contrib.gis.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from apps.core.models import User


class Vendor(models.Model):
    """
    Vendor model for suppliers in the B2B marketplace.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='vendor'
    )
    business_name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Legal business name"
    )
    slug = models.SlugField(
        max_length=250,
        unique=True,
        blank=True,
        help_text="URL-friendly version of business name"
    )
    description = models.TextField(
        blank=True,
        help_text="Business description"
    )
    phone_number = models.CharField(
        max_length=17,
        blank=True,
        help_text="Business contact number"
    )

    # Approval and Verification
    is_approved = models.BooleanField(
        default=False,
        help_text="Admin approval status"
    )
    fsa_verified = models.BooleanField(
        default=False,
        help_text="FSA verification completed"
    )
    stripe_onboarding_complete = models.BooleanField(
        default=False,
        help_text="Stripe Connect onboarding completed"
    )

    # Location fields (PostGIS)
    location = models.PointField(
        geography=True,
        help_text="Business location coordinates"
    )
    postcode = models.CharField(
        max_length=10,
        help_text="Business postcode"
    )
    delivery_radius_km = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum delivery radius in kilometers"
    )

    # FSA Integration
    fsa_establishment_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="FSA establishment ID"
    )
    fsa_rating_value = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="FSA hygiene rating (1-5)"
    )
    fsa_rating_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of last FSA inspection"
    )
    fsa_last_checked = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time we checked FSA API"
    )

    # Stripe Connect
    stripe_account_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Stripe Connect account ID"
    )
    commission_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0.10'),
        validators=[MinValueValidator(
            Decimal('0.00')), MaxValueValidator(Decimal('0.50'))],
        help_text="Marketplace commission rate (0.10 = 10%)"
    )

    # Business details
    vat_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="VAT registration number"
    )
    min_order_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Minimum order value in GBP"
    )
    logo_url = models.URLField(
        blank=True,
        help_text="URL to vendor logo"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendors'
        verbose_name = _('Vendor')
        verbose_name_plural = _('Vendors')
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_approved', 'stripe_onboarding_complete']),
            models.Index(fields=['fsa_rating_value']),
        ]

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.business_name)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Check if vendor is active and ready to sell."""
        return (
            self.is_approved and
            self.stripe_onboarding_complete and
            self.fsa_verified
        )

    @property
    def fsa_rating_display(self):
        """Return FSA rating as display text."""
        if self.fsa_rating_value:
            return f"{self.fsa_rating_value}/5"
        return "Not rated"
