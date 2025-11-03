# apps/products/models.py

import uuid
from decimal import Decimal
from django.contrib.gis.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from apps.vendors.models import Vendor


def product_image_path(instance, filename):
    """Generate unique path for product images."""
    ext = filename.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'
    return f'products/{instance.vendor.id}/{filename}'


class Category(models.Model):
    """
    Product categories with hierarchical structure.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'categories'
        verbose_name = _('Category')
        verbose_name_plural = _('Categories')
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['parent', 'is_active']),
        ]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Tag(models.Model):
    """
    Tags for products (dietary, organic, etc.)
    """
    TAG_TYPE_CHOICES = [
        ('dietary', 'Dietary'),
        ('organic', 'Organic/Sustainable'),
        ('origin', 'Origin'),
        ('preparation', 'Preparation'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)
    tag_type = models.CharField(
        max_length=20,
        choices=TAG_TYPE_CHOICES,
        default='other'
    )

    class Meta:
        db_table = 'tags'
        verbose_name = _('Tag')
        verbose_name_plural = _('Tags')
        ordering = ['tag_type', 'name']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['tag_type']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    Product model with allergen support and search capabilities.
    """
    UNIT_CHOICES = [
        ('kg', 'Kilogram'),
        ('g', 'Gram'),
        ('l', 'Litre'),
        ('ml', 'Millilitre'),
        ('unit', 'Unit'),
        ('case', 'Case'),
        ('box', 'Box'),
        ('bag', 'Bag'),
        ('bunch', 'Bunch'),
    ]

    # Common allergens for Natasha's Law compliance
    ALLERGEN_FIELDS = [
        'celery', 'cereals_containing_gluten', 'crustaceans', 'eggs',
        'fish', 'lupin', 'milk', 'molluscs', 'mustard', 'tree_nuts',
        'peanuts', 'sesame', 'soybeans', 'sulphur_dioxide'
    ]

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products'
    )

    # Basic information
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField()
    sku = models.CharField(
        max_length=50,
        unique=True,
        help_text="Stock Keeping Unit"
    )
    barcode = models.CharField(
        max_length=13,
        blank=True,
        help_text="EAN-13 barcode"
    )

    # Pricing
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    vat_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('0.20'),
        help_text="VAT rate (0.20 = 20%)"
    )
    unit = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='unit'
    )

    # Stock
    stock_quantity = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    low_stock_threshold = models.IntegerField(
        default=10,
        validators=[MinValueValidator(0)]
    )

    # Natasha's Law Compliance
    contains_allergens = models.BooleanField(default=False)
    allergen_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="Allergen information as JSON"
    )
    allergen_statement = models.TextField(
        blank=True,
        help_text="Free text allergen statement"
    )

    # Media - Updated for S3 storage
    primary_image = models.ImageField(
        upload_to=product_image_path,
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
        help_text="Primary product image"
    )
    additional_images = models.JSONField(
        default=list,
        blank=True,
        help_text="List of additional image URLs"
    )

    # Search
    search_vector = SearchVectorField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)

    # Tags
    tags = models.ManyToManyField(
        Tag,
        through='ProductTag',
        related_name='products',
        blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = _('Product')
        verbose_name_plural = _('Products')
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['category', '-created_at']),
            models.Index(fields=['vendor', 'stock_quantity']),
            models.Index(fields=['is_active', 'featured']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return f"{self.name} ({self.vendor.business_name})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.vendor.business_name}-{self.name}")
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        """Check if product is in stock."""
        return self.stock_quantity > 0

    @property
    def low_stock(self):
        """Check if product is low in stock."""
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def price_with_vat(self):
        """Calculate price including VAT."""
        return self.price * (1 + self.vat_rate)

    @property
    def vat_amount(self):
        """Calculate VAT amount."""
        return self.price * self.vat_rate


class ProductTag(models.Model):
    """
    Junction table for Product and Tag many-to-many relationship.
    Explicit model as shown in ERD.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='product_tags'
    )
    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name='tag_products'
    )

    class Meta:
        db_table = 'product_tags'
        verbose_name = _('Product Tag')
        verbose_name_plural = _('Product Tags')
        unique_together = [['product', 'tag']]
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['tag']),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.tag.name}"
