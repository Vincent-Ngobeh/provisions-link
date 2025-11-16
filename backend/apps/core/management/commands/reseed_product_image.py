# backend/apps/core/management/commands/reseed_product_image.py

import requests
from io import BytesIO
from django.core.management.base import BaseCommand
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.products.models import Product


class Command(BaseCommand):
    help = 'Reseed image for a specific product by name'

    def add_arguments(self, parser):
        parser.add_argument(
            '--product-name',
            type=str,
            required=True,
            help='Exact name of the product (e.g., "Jerk Chicken Pieces")',
        )
        parser.add_argument(
            '--search-query',
            type=str,
            default=None,
            help='Custom Unsplash search query (e.g., "jerk chicken caribbean grilled")',
        )

    def handle(self, *args, **options):
        product_name = options['product_name']
        search_query = options['search_query']

        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.WARNING('RESEED SINGLE PRODUCT IMAGE'))
        self.stdout.write('='*70 + '\n')

        # Find the product
        try:
            product = Product.objects.get(name=product_name)
        except Product.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Product "{product_name}" not found.\n')
            )
            self.stdout.write('Available products:')
            for p in Product.objects.all()[:10]:
                self.stdout.write(f'  - {p.name}')
            return
        except Product.MultipleObjectsReturned:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Multiple products found with name "{product_name}".\n')
            )
            return

        self.stdout.write(f'Found product: {product.name}')
        self.stdout.write(f'Vendor: {product.vendor.business_name}')

        # Determine search query
        if not search_query:
            # Use default from seed_product_images.py
            default_queries = {
                'Jerk Chicken Pieces': 'jerk chicken caribbean grilled',
                # Can add more defaults here
            }
            search_query = default_queries.get(
                product_name, product.category.name if product.category else 'food')
            self.stdout.write(
                f'Using default search query: "{search_query}"')
        else:
            self.stdout.write(f'Using custom search query: "{search_query}"')

        # Download new image from Unsplash
        self.stdout.write('\nDownloading new image from Unsplash...')
        try:
            image_file = self.download_unsplash_image(
                search_query, product.name)

            if not image_file:
                self.stdout.write(
                    self.style.ERROR('❌ Failed to download image from Unsplash'))
                return

            # Delete old image if exists
            if product.primary_image:
                self.stdout.write('Deleting old image...')
                product.primary_image.delete(save=False)

            # Upload new image
            product.primary_image = image_file
            product.save()

            self.stdout.write(
                self.style.SUCCESS(f'\n✅ Successfully updated image for "{product.name}"!'))
            self.stdout.write(f'Image URL: {product.primary_image.url}\n')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error: {str(e)}\n'))

        self.stdout.write('='*70 + '\n')

    def download_unsplash_image(self, search_query, product_name):
        """
        Download image from Unsplash API.
        Returns SimpleUploadedFile or None if failed.
        """
        try:
            # Use source.unsplash.com (no API key needed)
            url = f'https://source.unsplash.com/800x600/?{search_query.replace(" ", ",")}'

            self.stdout.write(f'Fetching: {url}')
            response = requests.get(url, timeout=10, allow_redirects=True)

            self.stdout.write(f'Response status code: {response.status_code}')
            self.stdout.write(
                f'Response content type: {response.headers.get("content-type", "unknown")}')
            self.stdout.write(
                f'Response content length: {len(response.content)} bytes')

            if response.status_code == 200:
                # Check if we actually got an image
                content_type = response.headers.get('content-type', '')
                if 'image' not in content_type:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠️  Response is not an image (content-type: {content_type})')
                    )
                    # Print first 500 chars of response to see what we got
                    self.stdout.write(
                        f'Response preview: {response.text[:500]}')
                    return None

                # Create file from response
                image_file = SimpleUploadedFile(
                    f"{product_name.lower().replace(' ', '_')}.jpg",
                    response.content,
                    content_type='image/jpeg'
                )
                return image_file
            else:
                self.stdout.write(
                    f'❌ HTTP {response.status_code}: {response.text[:200]}')
                return None

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Download error: {type(e).__name__}: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())
            return None
