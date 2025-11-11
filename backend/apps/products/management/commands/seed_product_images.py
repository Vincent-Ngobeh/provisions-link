# backend/apps/products/management/commands/seed_product_images.py

import os
import requests
import time
from io import BytesIO
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw, ImageFont
from apps.products.models import Product
from apps.vendors.models import Vendor


class Command(BaseCommand):
    help = 'Seed product images from Unsplash API (idempotent - safe to run multiple times)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--use-placeholders',
            action='store_true',
            help='Use generated placeholder images instead of downloading from Unsplash',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            help='Skip products that already have images',
        )

    def handle(self, *args, **options):
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.WARNING('SEEDING PRODUCT IMAGES'))
        self.stdout.write('='*70 + '\n')

        use_placeholders = options['use_placeholders']
        skip_existing = options['skip_existing']

        # Unsplash API configuration (using public demo access)
        # For production, get your own free API key from https://unsplash.com/developers
        self.unsplash_access_key = os.getenv('UNSPLASH_ACCESS_KEY', 'demo')

        if not use_placeholders and self.unsplash_access_key == 'demo':
            self.stdout.write(
                self.style.WARNING(
                    'ℹ️  Using Unsplash public demo access (limited requests)\n'
                    '   For production, set UNSPLASH_ACCESS_KEY in .env\n'
                    '   Get free key at: https://unsplash.com/developers\n'
                )
            )

        # Map product names to Unsplash search queries
        # This maps your exact hardcoded product names to appropriate image searches
        self.image_search_mapping = {
            # Borough Market Organics
            'Heritage Tomatoes Mix': 'heritage tomatoes colorful',
            'Baby Leaf Salad Mix': 'salad greens leaves',
            'Seasonal Root Vegetable Box': 'root vegetables carrots',

            # Smithfield Premium Meats
            'Grass-Fed Beef Ribeye': 'beef ribeye steak raw',
            'Free-Range Chicken Breast': 'chicken breast raw',
            'British Lamb Shoulder': 'lamb shoulder raw meat',

            # Spitalfields Artisan Dairy
            'Organic Whole Milk': 'milk bottle glass fresh',
            'Farmhouse Cheddar': 'cheddar cheese wheel',
            'Free-Range Eggs Large': 'brown eggs basket',
            'Double Cream': 'cream pouring jug',

            # Covent Garden Artisan Bakery
            'Sourdough Loaf': 'sourdough bread loaf',
            'Croissants': 'croissant pastry french',
            'Baguette Tradition': 'french baguette bread',

            # Shoreditch Fresh Seafood
            'Scottish Salmon Fillet': 'salmon fillet fresh',
            'Cornish Sea Bass Whole': 'sea bass fish whole',
            'Scallops Hand-Dived': 'scallops fresh seafood',

            # Hackney Provisions Co
            'Extra Virgin Olive Oil': 'olive oil bottle',
            'Japanese Soy Sauce': 'soy sauce bottle',
            'Arborio Risotto Rice': 'arborio rice grains',
            'Smoked Paprika': 'paprika spice powder',

            # Greenwich Urban Greens
            'Microgreens Mix': 'microgreens sprouts',
            'Baby Basil': 'basil plant fresh',
            'Pea Shoots': 'pea shoots microgreens',

            # Brixton Traditional Butchers
            'Jerk Chicken Pieces': 'chicken pieces marinated',
            'Oxtail': 'oxtail meat raw',
            'Goat Curry Pieces': 'goat meat curry pieces',
        }

        # Get all products
        products = Product.objects.select_related('vendor').all()

        if not products.exists():
            self.stdout.write(
                self.style.ERROR('No products found. Run seed_products first.')
            )
            return

        total_products = products.count()
        updated_count = 0
        skipped_count = 0
        failed_count = 0

        self.stdout.write(f'Found {total_products} products\n')

        for idx, product in enumerate(products, 1):
            # Skip if already has image and skip_existing is True
            if skip_existing and product.primary_image:
                self.stdout.write(
                    f'  [{idx}/{total_products}] ⏭️  {product.name[:40]} - Already has image (skipped)'
                )
                skipped_count += 1
                continue

            # Get search query for this product
            search_query = self.image_search_mapping.get(
                product.name,
                product.category.name if product.category else 'food'
            )

            try:
                if use_placeholders:
                    # Generate placeholder image
                    image_file = self.generate_placeholder_image(product)
                else:
                    # Try to download from Unsplash
                    image_file = self.download_unsplash_image(
                        search_query, product.name)

                    if not image_file:
                        # Fallback to placeholder
                        self.stdout.write(
                            f'  [{idx}/{total_products}] ⚠️  {product.name[:40]} - Download failed, using placeholder'
                        )
                        image_file = self.generate_placeholder_image(product)

                # Delete old image if exists
                if product.primary_image:
                    product.primary_image.delete(save=False)

                # Upload new image
                product.primary_image = image_file
                product.save()

                updated_count += 1
                self.stdout.write(
                    f'  [{idx}/{total_products}] ✅ {product.name[:40]} - Image uploaded'
                )

                # Rate limiting for Unsplash API (50 requests per hour on demo)
                if not use_placeholders and self.unsplash_access_key == 'demo':
                    time.sleep(0.5)  # Be nice to the API

            except Exception as e:
                failed_count += 1
                self.stdout.write(
                    f'  [{idx}/{total_products}] ❌ {product.name[:40]} - Failed: {str(e)}'
                )

        # Summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'✅ IMAGE SEEDING COMPLETE'))
        self.stdout.write('='*70)
        self.stdout.write(f'\nResults:')
        self.stdout.write(f'  Total Products: {total_products}')
        self.stdout.write(f'  Updated: {updated_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Failed: {failed_count}')
        self.stdout.write('')

        if not use_placeholders and updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n📸 Images uploaded to S3 and ready to view!\n'
                )
            )

    def download_unsplash_image(self, search_query, product_name):
        """
        Download image from Unsplash API.
        Returns SimpleUploadedFile or None if failed.
        """
        try:
            # Unsplash API endpoint
            if self.unsplash_access_key == 'demo':
                # Use source.unsplash.com for demo (no API key needed)
                # This is rate-limited but works for testing
                url = f'https://source.unsplash.com/800x600/?{search_query.replace(" ", ",")}'
                response = requests.get(url, timeout=10)
            else:
                # Use official API with access key
                api_url = 'https://api.unsplash.com/photos/random'
                params = {
                    'query': search_query,
                    'orientation': 'landscape',
                    'client_id': self.unsplash_access_key
                }
                response = requests.get(api_url, params=params, timeout=10)

                if response.status_code != 200:
                    return None

                data = response.json()
                image_url = data['urls']['regular']  # 1080px wide
                response = requests.get(image_url, timeout=10)

            if response.status_code == 200:
                # Create file from response
                image_file = SimpleUploadedFile(
                    f"{product_name.lower().replace(' ', '_')}.jpg",
                    response.content,
                    content_type='image/jpeg'
                )
                return image_file

            return None

        except Exception as e:
            # Silently fail and return None (fallback will be used)
            return None

    def generate_placeholder_image(self, product):
        """
        Generate a placeholder image with product name and category.
        This is the fallback if Unsplash download fails.
        """
        # Create image with category-based color
        colors = {
            'Fresh Produce': '#4CAF50',
            'Meat & Poultry': '#F44336',
            'Seafood': '#2196F3',
            'Dairy & Eggs': '#FFF9C4',
            'Bakery': '#FF9800',
            'Pantry Staples': '#9E9E9E',
            'Herbs & Spices': '#8BC34A',
            'Oils & Condiments': '#FFD700',
            'Beverages': '#00BCD4',
            'Specialty Foods': '#9C27B0',
        }

        # Get parent category name
        category = product.category
        parent_category_name = category.parent.name if category and category.parent else (
            category.name if category else 'Product')
        color = colors.get(parent_category_name, '#607D8B')

        # Create image
        img = Image.new('RGB', (800, 600), color=color)
        draw = ImageDraw.Draw(img)

        # Add semi-transparent overlay
        overlay = Image.new('RGBA', (800, 600), (255, 255, 255, 128))
        img.paste(overlay, (0, 0), overlay)

        # Try to use a nicer font, fallback to default
        try:
            # Try to load a system font
            font_large = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
            font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            # Fallback to default font
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        # Draw product name (wrap text if too long)
        product_name = product.name
        if len(product_name) > 25:
            # Split into two lines
            words = product_name.split()
            mid = len(words) // 2
            line1 = ' '.join(words[:mid])
            line2 = ' '.join(words[mid:])

            # Get bounding boxes
            bbox1 = draw.textbbox((0, 0), line1, font=font_large)
            bbox2 = draw.textbbox((0, 0), line2, font=font_large)
            w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
            w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

            draw.text((400 - w1/2, 250 - h1), line1,
                      fill='#333', font=font_large)
            draw.text((400 - w2/2, 300), line2, fill='#333', font=font_large)
        else:
            bbox = draw.textbbox((0, 0), product_name, font=font_large)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((400 - w/2, 270 - h/2), product_name,
                      fill='#333', font=font_large)

        # Draw category
        category_text = parent_category_name
        bbox = draw.textbbox((0, 0), category_text, font=font_small)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((400 - w/2, 350), category_text,
                  fill='#666', font=font_small)

        # Draw vendor name
        vendor_text = product.vendor.business_name
        bbox = draw.textbbox((0, 0), vendor_text, font=font_small)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((400 - w/2, 400), vendor_text, fill='#666', font=font_small)

        # Draw price
        price_text = f"£{product.price}"
        bbox = draw.textbbox((0, 0), price_text, font=font_large)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((400 - w/2, 470), price_text, fill='#333', font=font_large)

        # Save to BytesIO
        img_bytes = BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        # Create Django file
        image_file = SimpleUploadedFile(
            f"{product.name.lower().replace(' ', '_')}.png",
            img_bytes.read(),
            content_type='image/png'
        )

        return image_file
