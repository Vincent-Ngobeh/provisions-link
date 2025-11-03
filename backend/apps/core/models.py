# apps/core/models.py

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.gis.db import models
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """
    Custom user manager for email-based authentication.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a regular user with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email field must be set'))

        email = self.normalize_email(email)

        # Set username to email if not provided
        if 'username' not in extra_fields:
            extra_fields['username'] = email

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Create and save a superuser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User model extending AbstractUser.
    Uses email for authentication instead of username.
    """
    # Override username to make it optional and non-unique
    username = models.CharField(
        _('username'),
        max_length=150,
        unique=False,
        blank=True,
        null=True,
        help_text=_(
            'Optional. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
    )

    email = models.EmailField(
        _('email address'),
        unique=True,
        error_messages={
            'unique': _("A user with that email already exists."),
        },
    )

    phone_regex = RegexValidator(
        regex=r'^(?:(?:\+44)|(?:0))(?:\d\s?){10,11}$',
        message="Phone number must be entered in the format: '+44' or '0' followed by 10-11 digits."
    )
    phone_number = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        help_text="UK phone number"
    )

    # Use email as the username field
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Email is already required as USERNAME_FIELD

    # Use custom manager
    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self):
        return self.email


class Address(models.Model):
    """
    User addresses for delivery.
    """
    ADDRESS_TYPE_CHOICES = [
        ('home', 'Home'),
        ('work', 'Work'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    address_name = models.CharField(
        max_length=50,
        choices=ADDRESS_TYPE_CHOICES,
        default='home'
    )
    recipient_name = models.CharField(max_length=100)
    phone_number = models.CharField(
        max_length=17,
        help_text="Contact number for delivery"
    )
    line1 = models.CharField(max_length=255, verbose_name="Address Line 1")
    line2 = models.CharField(max_length=255, blank=True,
                             verbose_name="Address Line 2")
    city = models.CharField(max_length=100)
    postcode = models.CharField(max_length=10)
    country = models.CharField(max_length=2, default='GB')

    # PostGIS field for location-based queries
    location = models.PointField(geography=True, null=True, blank=True)

    is_default = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'addresses'
        verbose_name = _('Address')
        verbose_name_plural = _('Addresses')
        # REMOVED: unique_together constraint to allow multiple addresses with same type
        indexes = [
            models.Index(fields=['user', 'is_default']),
        ]

    def __str__(self):
        return f"{self.address_name} - {self.postcode}"

    def save(self, *args, **kwargs):
        # Normalize postcode format
        if self.postcode:
            # Remove all spaces and convert to uppercase
            clean = self.postcode.upper().replace(' ', '')
            # Add space before last 3 characters for UK format
            if len(clean) >= 5:
                self.postcode = f"{clean[:-3]} {clean[-3:]}"

        # If this is set as default, unset other defaults for this user
        if self.is_default:
            Address.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)


class PrivacySettings(models.Model):
    """
    GDPR-compliant privacy settings for users.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='privacy_settings'
    )
    marketing_emails = models.BooleanField(
        default=False,
        help_text="Receive marketing emails and promotions"
    )
    order_updates = models.BooleanField(
        default=True,
        help_text="Receive order status updates"
    )
    data_sharing = models.BooleanField(
        default=False,
        help_text="Allow anonymized data sharing with partners"
    )
    analytics_tracking = models.BooleanField(
        default=False,
        help_text="Allow analytics tracking for improved experience"
    )

    # Timestamps
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'privacy_settings'
        verbose_name = _('Privacy Settings')
        verbose_name_plural = _('Privacy Settings')

    def __str__(self):
        return f"Privacy settings for {self.user.email}"
