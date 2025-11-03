# backend/apps/products/management/commands/seed_products.py

from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.products.models import Product, Category, Tag
from apps.vendors.models import Vendor


class Command(BaseCommand):
    help = 'Seed products for vendors (streamlined version with 3-5 products each)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing products before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            Product.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared existing products'))

        vendors = Vendor.objects.all()
        if not vendors.exists():
            self.stdout.write(
                self.style.ERROR('No vendors found. Run seed_vendors first.')
            )
            return

        categories = Category.objects.all()
        if not categories.exists():
            self.stdout.write(
                self.style.ERROR(
                    'No categories found. Run seed_categories first.')
            )
            return

        tags = {tag.name: tag for tag in Tag.objects.all()}

        # Streamlined product definitions (3-5 products per vendor)
        products_by_vendor = {
            'Borough Market Organics': [
                {
                    'name': 'Heritage Tomatoes Mix',
                    'category': 'Seasonal Vegetables',
                    'price': Decimal('18.50'),
                    'unit': 'kg',
                    'stock': 45,
                    'description': 'Assorted heritage variety tomatoes including Black Krim, Green Zebra, and Brandywine.',
                    'tags': ['Organic', 'British', 'Seasonal'],
                    'allergens': {},
                    'barcode': '5060123456001',
                },
                {
                    'name': 'Baby Leaf Salad Mix',
                    'category': 'Salad Leaves',
                    'price': Decimal('12.00'),
                    'unit': 'kg',
                    'stock': 60,
                    'description': 'Premium mix of baby spinach, rocket, and mizuna. Washed and ready to use.',
                    'tags': ['Organic', 'Local', 'Fresh'],
                    'allergens': {},
                    'barcode': '5060123456002',
                },
                {
                    'name': 'Seasonal Root Vegetable Box',
                    'category': 'Root Vegetables',
                    'price': Decimal('24.00'),
                    'unit': 'box',
                    'stock': 30,
                    'description': 'Assorted seasonal root vegetables. Approximately 5kg per box.',
                    'tags': ['Organic', 'British', 'Seasonal'],
                    'allergens': {'celery': True},
                    'barcode': '5060123456003',
                },
            ],
            'Smithfield Premium Meats': [
                {
                    'name': 'Grass-Fed Beef Ribeye',
                    'category': 'British Beef',
                    'price': Decimal('45.00'),
                    'unit': 'kg',
                    'stock': 35,
                    'description': '28-day dry-aged grass-fed beef ribeye from Scottish farms.',
                    'tags': ['British', 'Grass-Fed', 'Scottish'],
                    'allergens': {},
                    'barcode': '5060234567001',
                },
                {
                    'name': 'Free-Range Chicken Breast',
                    'category': 'Free-Range Chicken',
                    'price': Decimal('18.50'),
                    'unit': 'kg',
                    'stock': 60,
                    'description': 'Premium free-range chicken breasts from RSPCA Assured farms.',
                    'tags': ['Free-Range', 'British', 'Halal'],
                    'allergens': {},
                    'barcode': '5060234567002',
                },
                {
                    'name': 'British Lamb Shoulder',
                    'category': 'British Lamb',
                    'price': Decimal('22.00'),
                    'unit': 'kg',
                    'stock': 28,
                    'description': 'Bone-in lamb shoulder from Welsh hill farms.',
                    'tags': ['British', 'Grass-Fed', 'Halal'],
                    'allergens': {},
                    'barcode': '5060234567003',
                },
            ],
            'Spitalfields Artisan Dairy': [
                {
                    'name': 'Organic Whole Milk',
                    'category': 'Milk & Cream',
                    'price': Decimal('2.80'),
                    'unit': 'l',
                    'stock': 100,
                    'description': 'Fresh organic whole milk from single-herd farms.',
                    'tags': ['Organic', 'British', 'Vegetarian'],
                    'allergens': {'milk': True},
                    'barcode': '5060345678001',
                },
                {
                    'name': 'Farmhouse Cheddar',
                    'category': 'Artisan Cheese',
                    'price': Decimal('24.00'),
                    'unit': 'kg',
                    'stock': 45,
                    'description': 'Traditional cloth-bound farmhouse cheddar, aged 12 months.',
                    'tags': ['British', 'Vegetarian', 'Award Winner'],
                    'allergens': {'milk': True},
                    'barcode': '5060345678002',
                },
                {
                    'name': 'Free-Range Eggs Large',
                    'category': 'Free-Range Eggs',
                    'price': Decimal('3.50'),
                    'unit': 'unit',
                    'stock': 200,
                    'description': 'Free-range large eggs from local farms. Sold in trays of 30.',
                    'tags': ['Free-Range', 'Local', 'Vegetarian'],
                    'allergens': {'eggs': True},
                    'barcode': '5060345678003',
                },
                {
                    'name': 'Double Cream',
                    'category': 'Milk & Cream',
                    'price': Decimal('5.50'),
                    'unit': 'l',
                    'stock': 60,
                    'description': 'Rich double cream with 48% fat content.',
                    'tags': ['British', 'Vegetarian'],
                    'allergens': {'milk': True},
                    'barcode': '5060345678004',
                },
            ],
            'Covent Garden Artisan Bakery': [
                {
                    'name': 'Sourdough Loaf',
                    'category': 'Sourdough',
                    'price': Decimal('4.50'),
                    'unit': 'unit',
                    'stock': 80,
                    'description': 'Traditional sourdough with 48-hour fermentation.',
                    'tags': ['Organic', 'Vegetarian', 'Vegan'],
                    'allergens': {'cereals_containing_gluten': True},
                    'barcode': '5060456789001',
                },
                {
                    'name': 'Croissants',
                    'category': 'Pastries',
                    'price': Decimal('16.00'),
                    'unit': 'unit',
                    'stock': 70,
                    'description': 'Butter croissants with 27 layers. Box of 12.',
                    'tags': ['French', 'Vegetarian'],
                    'allergens': {'cereals_containing_gluten': True, 'milk': True, 'eggs': True},
                    'barcode': '5060456789002',
                },
                {
                    'name': 'Baguette Tradition',
                    'category': 'Bakery',
                    'price': Decimal('2.80'),
                    'unit': 'unit',
                    'stock': 100,
                    'description': 'Classic French baguette baked fresh daily.',
                    'tags': ['French', 'Vegetarian', 'Vegan'],
                    'allergens': {'cereals_containing_gluten': True},
                    'barcode': '5060456789003',
                },
            ],
            'Shoreditch Fresh Seafood': [
                {
                    'name': 'Scottish Salmon Fillet',
                    'category': 'Fresh Fish',
                    'price': Decimal('32.00'),
                    'unit': 'kg',
                    'stock': 40,
                    'description': 'Premium Scottish salmon fillets. Pin-boned and skin-on.',
                    'tags': ['Scottish', 'British', 'Fresh'],
                    'allergens': {'fish': True},
                    'barcode': '5060567890001',
                },
                {
                    'name': 'Cornish Sea Bass Whole',
                    'category': 'Fresh Fish',
                    'price': Decimal('28.00'),
                    'unit': 'kg',
                    'stock': 25,
                    'description': 'Line-caught Cornish sea bass. Sold whole, gutted and scaled.',
                    'tags': ['British', 'Cornish', 'MSC Certified', 'Sustainable'],
                    'allergens': {'fish': True},
                    'barcode': '5060567890002',
                },
                {
                    'name': 'Scallops Hand-Dived',
                    'category': 'Shellfish',
                    'price': Decimal('48.00'),
                    'unit': 'kg',
                    'stock': 20,
                    'description': 'Hand-dived king scallops from Scottish waters.',
                    'tags': ['Scottish', 'British', 'Sustainable', 'Chef Favorite'],
                    'allergens': {'molluscs': True},
                    'barcode': '5060567890003',
                },
            ],
            'Hackney Provisions Co': [
                {
                    'name': 'Extra Virgin Olive Oil',
                    'category': 'Oils & Condiments',
                    'price': Decimal('22.00'),
                    'unit': 'l',
                    'stock': 50,
                    'description': 'Single-estate extra virgin olive oil from Tuscany. 5L tin.',
                    'tags': ['Italian', 'Vegan'],
                    'allergens': {},
                    'barcode': '5060678901001',
                },
                {
                    'name': 'Japanese Soy Sauce',
                    'category': 'Oils & Condiments',
                    'price': Decimal('18.00'),
                    'unit': 'l',
                    'stock': 60,
                    'description': 'Naturally brewed Japanese soy sauce. 5L container.',
                    'tags': ['Vegan'],
                    'allergens': {'soybeans': True, 'cereals_containing_gluten': True},
                    'barcode': '5060678901002',
                },
                {
                    'name': 'Arborio Risotto Rice',
                    'category': 'Pantry Staples',
                    'price': Decimal('4.50'),
                    'unit': 'kg',
                    'stock': 80,
                    'description': 'Italian Arborio rice perfect for risotto. 5kg sack.',
                    'tags': ['Italian', 'Vegan'],
                    'allergens': {},
                    'barcode': '5060678901003',
                },
                {
                    'name': 'Smoked Paprika',
                    'category': 'Herbs & Spices',
                    'price': Decimal('15.00'),
                    'unit': 'kg',
                    'stock': 45,
                    'description': 'Spanish smoked paprika (pimentón).',
                    'tags': ['Vegan'],
                    'allergens': {},
                    'barcode': '5060678901004',
                },
            ],
            'Greenwich Urban Greens': [
                {
                    'name': 'Microgreens Mix',
                    'category': 'Microgreens',
                    'price': Decimal('45.00'),
                    'unit': 'kg',
                    'stock': 12,
                    'description': 'Assorted microgreens. Harvested to order within 24 hours.',
                    'tags': ['Local', 'Vegan', 'Fresh', 'Sustainable'],
                    'allergens': {},
                    'barcode': '5060789012001',
                },
                {
                    'name': 'Baby Basil',
                    'category': 'Microgreens',
                    'price': Decimal('38.00'),
                    'unit': 'kg',
                    'stock': 8,
                    'description': 'Living baby basil plants. Zero food miles.',
                    'tags': ['Local', 'Vegan', 'Fresh'],
                    'allergens': {},
                    'barcode': '5060789012002',
                },
                {
                    'name': 'Pea Shoots',
                    'category': 'Microgreens',
                    'price': Decimal('28.00'),
                    'unit': 'kg',
                    'stock': 15,
                    'description': 'Tender pea shoots with sweet flavor.',
                    'tags': ['Local', 'Vegan', 'Fresh'],
                    'allergens': {},
                    'barcode': '5060789012003',
                },
            ],
            'Brixton Traditional Butchers': [
                {
                    'name': 'Jerk Chicken Pieces',
                    'category': 'Free-Range Chicken',
                    'price': Decimal('14.00'),
                    'unit': 'kg',
                    'stock': 25,
                    'description': 'Free-range chicken marinated in house-made jerk spices.',
                    'tags': ['Free-Range', 'British', 'Pre-Marinated', 'Ready-to-Cook'],
                    'allergens': {},
                    'barcode': '5060890123001',
                },
                {
                    'name': 'Oxtail',
                    'category': 'British Beef',
                    'price': Decimal('18.00'),
                    'unit': 'kg',
                    'stock': 15,
                    'description': 'Grass-fed beef oxtail. Perfect for slow-braised stews.',
                    'tags': ['British', 'Grass-Fed'],
                    'allergens': {},
                    'barcode': '5060890123002',
                },
                {
                    'name': 'Goat Curry Pieces',
                    'category': 'Meat & Poultry',
                    'price': Decimal('16.00'),
                    'unit': 'kg',
                    'stock': 12,
                    'description': 'Bone-in goat pieces perfect for Caribbean-style curry.',
                    'tags': ['British', 'Halal'],
                    'allergens': {},
                    'barcode': '5060890123003',
                },
            ],
        }

        created_count = 0
        vendor_counts = {}

        for vendor_name, products in products_by_vendor.items():
            try:
                vendor = Vendor.objects.get(business_name=vendor_name)
            except Vendor.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f'Vendor "{vendor_name}" not found, skipping...')
                )
                continue

            vendor_counts[vendor_name] = 0

            for prod_data in products:
                # Get category
                try:
                    category = Category.objects.get(name=prod_data['category'])
                except Category.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Category "{prod_data["category"]}" not found, skipping...')
                    )
                    continue

                # Generate SKU
                sku = f"{vendor.business_name[:3].upper()}-{prod_data['barcode'][-4:]}"

                # Create product
                product, created = Product.objects.get_or_create(
                    vendor=vendor,
                    sku=sku,
                    defaults={
                        'category': category,
                        'name': prod_data['name'],
                        'description': prod_data['description'],
                        'price': prod_data['price'],
                        'unit': prod_data['unit'],
                        'stock_quantity': prod_data['stock'],
                        'low_stock_threshold': 10,
                        'barcode': prod_data['barcode'],
                        'contains_allergens': bool(prod_data['allergens']),
                        'allergen_info': prod_data['allergens'],
                        'is_active': True,
                    }
                )

                if created:
                    # Add tags
                    tag_objects = []
                    for tag_name in prod_data.get('tags', []):
                        if tag_name in tags:
                            tag_objects.append(tags[tag_name])

                    if tag_objects:
                        product.tags.set(tag_objects)

                    created_count += 1
                    vendor_counts[vendor_name] += 1

                    # Display with stock indicator
                    stock_indicator = '✓' if product.in_stock else '✗'
                    allergen_indicator = '⚠️' if product.contains_allergens else '  '

                    self.stdout.write(
                        f"  {stock_indicator} {allergen_indicator} £{product.price:6} | {product.name[:40]}"
                    )

        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Created {created_count} products')
        )

        # Summary by vendor
        self.stdout.write('\nProducts by Vendor:')
        for vendor_name, count in vendor_counts.items():
            self.stdout.write(f'  {vendor_name}: {count} products')

        # Overall statistics
        total_products = Product.objects.count()
        in_stock = Product.objects.filter(stock_quantity__gt=0).count()
        low_stock = Product.objects.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=10
        ).count()
        out_of_stock = Product.objects.filter(stock_quantity=0).count()
        with_allergens = Product.objects.filter(
            contains_allergens=True).count()

        self.stdout.write('\nProduct Statistics:')
        self.stdout.write(f'  Total: {total_products}')
        self.stdout.write(f'  In Stock: {in_stock}')
        self.stdout.write(f'  Low Stock: {low_stock}')
        self.stdout.write(f'  Out of Stock: {out_of_stock}')
        self.stdout.write(f'  With Allergens: {with_allergens}')
