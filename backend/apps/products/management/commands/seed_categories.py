# backend/apps/products/management/commands/seed_categories.py

from django.core.management.base import BaseCommand
from apps.products.models import Category, Tag


class Command(BaseCommand):
    help = 'Seed product categories and tags for portfolio demonstration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing categories and tags before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            Category.objects.all().delete()
            Tag.objects.all().delete()
            self.stdout.write(self.style.WARNING(
                'Cleared existing categories and tags'))

        # Create main categories
        categories_data = [
            {'name': 'Fresh Produce', 'display_order': 1},
            {'name': 'Meat & Poultry', 'display_order': 2},
            {'name': 'Seafood', 'display_order': 3},
            {'name': 'Dairy & Eggs', 'display_order': 4},
            {'name': 'Bakery', 'display_order': 5},
            {'name': 'Pantry Staples', 'display_order': 6},
            {'name': 'Herbs & Spices', 'display_order': 7},
            {'name': 'Oils & Condiments', 'display_order': 8},
            {'name': 'Beverages', 'display_order': 9},
            {'name': 'Specialty Foods', 'display_order': 10},
        ]

        categories_created = 0
        category_objects = {}

        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'display_order': cat_data['display_order']}
            )
            category_objects[cat_data['name']] = category
            if created:
                categories_created += 1
                self.stdout.write(f"  ✓ {category.name}")

        # Create subcategories
        subcategories_data = [
            {'name': 'Salad Leaves', 'parent': 'Fresh Produce', 'display_order': 1},
            {'name': 'Root Vegetables', 'parent': 'Fresh Produce', 'display_order': 2},
            {'name': 'Seasonal Vegetables',
                'parent': 'Fresh Produce', 'display_order': 3},
            {'name': 'Fresh Fruits', 'parent': 'Fresh Produce', 'display_order': 4},
            {'name': 'Microgreens', 'parent': 'Fresh Produce', 'display_order': 5},

            {'name': 'British Beef', 'parent': 'Meat & Poultry', 'display_order': 1},
            {'name': 'British Lamb', 'parent': 'Meat & Poultry', 'display_order': 2},
            {'name': 'Free-Range Chicken',
                'parent': 'Meat & Poultry', 'display_order': 3},
            {'name': 'Pork & Bacon', 'parent': 'Meat & Poultry', 'display_order': 4},

            {'name': 'Fresh Fish', 'parent': 'Seafood', 'display_order': 1},
            {'name': 'Shellfish', 'parent': 'Seafood', 'display_order': 2},

            {'name': 'Artisan Cheese', 'parent': 'Dairy & Eggs', 'display_order': 1},
            {'name': 'Milk & Cream', 'parent': 'Dairy & Eggs', 'display_order': 2},
            {'name': 'Free-Range Eggs', 'parent': 'Dairy & Eggs', 'display_order': 3},

            {'name': 'Sourdough', 'parent': 'Bakery', 'display_order': 1},
            {'name': 'Pastries', 'parent': 'Bakery', 'display_order': 2},
        ]

        for subcat_data in subcategories_data:
            parent_name = subcat_data.pop('parent')
            parent = category_objects.get(parent_name)

            if parent:
                subcat, created = Category.objects.get_or_create(
                    name=subcat_data['name'],
                    defaults={
                        'parent': parent,
                        'display_order': subcat_data['display_order']
                    }
                )
                if created:
                    categories_created += 1
                    self.stdout.write(f"    ↳ {subcat.name}")

        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Created {categories_created} categories')
        )

        # Create tags
        tags_data = [
            # Dietary tags
            {'name': 'Vegan', 'tag_type': 'dietary'},
            {'name': 'Vegetarian', 'tag_type': 'dietary'},
            {'name': 'Gluten-Free', 'tag_type': 'dietary'},
            {'name': 'Dairy-Free', 'tag_type': 'dietary'},
            {'name': 'Halal', 'tag_type': 'dietary'},
            {'name': 'Kosher', 'tag_type': 'dietary'},

            # Organic/Sustainable tags
            {'name': 'Organic', 'tag_type': 'organic'},
            {'name': 'Free-Range', 'tag_type': 'organic'},
            {'name': 'Grass-Fed', 'tag_type': 'organic'},
            {'name': 'MSC Certified', 'tag_type': 'organic'},
            {'name': 'Sustainable', 'tag_type': 'organic'},
            {'name': 'Heritage Breed', 'tag_type': 'organic'},
            {'name': 'Biodynamic', 'tag_type': 'organic'},

            # Origin tags
            {'name': 'British', 'tag_type': 'origin'},
            {'name': 'Local', 'tag_type': 'origin'},
            {'name': 'Scottish', 'tag_type': 'origin'},
            {'name': 'Cornish', 'tag_type': 'origin'},
            {'name': 'French', 'tag_type': 'origin'},
            {'name': 'Italian', 'tag_type': 'origin'},
            {'name': 'Mediterranean', 'tag_type': 'origin'},

            # Preparation tags
            {'name': 'Ready-to-Cook', 'tag_type': 'preparation'},
            {'name': 'Pre-Marinated', 'tag_type': 'preparation'},
            {'name': 'Frozen', 'tag_type': 'preparation'},
            {'name': 'Fresh', 'tag_type': 'preparation'},

            # Other tags
            {'name': 'Award Winner', 'tag_type': 'other'},
            {'name': 'Seasonal', 'tag_type': 'other'},
            {'name': 'Chef Favorite', 'tag_type': 'other'},
            {'name': 'New Arrival', 'tag_type': 'other'},
        ]

        tags_created = 0
        tag_counts = {
            'dietary': 0,
            'organic': 0,
            'origin': 0,
            'preparation': 0,
            'other': 0
        }

        for tag_data in tags_data:
            tag, created = Tag.objects.get_or_create(
                name=tag_data['name'],
                defaults={'tag_type': tag_data['tag_type']}
            )
            if created:
                tags_created += 1
                tag_counts[tag_data['tag_type']] += 1

        self.stdout.write(
            self.style.SUCCESS(f'\n✅ Created {tags_created} tags')
        )

        # Tag statistics
        self.stdout.write('\nTag Distribution:')
        for tag_type, count in tag_counts.items():
            self.stdout.write(f'  {tag_type.capitalize()}: {count}')

        # Summary
        total_categories = Category.objects.count()
        parent_categories = Category.objects.filter(
            parent__isnull=True).count()
        subcategories = Category.objects.filter(parent__isnull=False).count()
        total_tags = Tag.objects.count()

        self.stdout.write('\nFinal Statistics:')
        self.stdout.write(
            f'  Categories: {total_categories} ({parent_categories} parent, {subcategories} sub)')
        self.stdout.write(f'  Tags: {total_tags}')
