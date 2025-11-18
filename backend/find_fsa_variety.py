"""
FSA Establishment ID Finder - Rating Variety Search
Searches for establishments with 3★, 4★, and 5★ ratings
"""
import requests
import csv
from datetime import datetime
from collections import defaultdict


def search_fsa_establishments(postcode_area, page_size=50):
    """Search FSA API for establishments in a postcode area."""
    url = "https://api.ratings.food.gov.uk/Establishments"
    headers = {
        'x-api-version': '2',
        'Accept': 'application/json'
    }
    params = {
        'address': postcode_area,
        'pageSize': page_size
    }

    print(f"   Searching FSA API for {postcode_area}...")

    try:
        response = requests.get(url, headers=headers,
                                params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        total = len(data.get('establishments', []))
        print(f"   ✓ Found {total} total establishments")
        return data
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return None


def categorize_by_rating(data):
    """Categorize establishments by rating (3★, 4★, 5★)."""
    if not data or 'establishments' not in data:
        return {}

    by_rating = defaultdict(list)

    for est in data['establishments']:
        rating = est.get('RatingValue', '')

        if rating in ['3', '4', '5']:
            by_rating[rating].append({
                'fsa_id': est.get('FHRSID'),
                'business_name': est.get('BusinessName', ''),
                'business_type': est.get('BusinessType', ''),
                'rating': rating,
                'postcode': est.get('PostCode', ''),
                'address_line1': est.get('AddressLine1', ''),
                'rating_date': est.get('RatingDate', '')[:10] if est.get('RatingDate') else 'N/A',
                'local_authority': est.get('LocalAuthorityName', ''),
                'scheme_type': est.get('SchemeType', '')
            })

    for rating in by_rating:
        by_rating[rating].sort(key=lambda x: x['rating_date'], reverse=True)

    return by_rating


def display_rating_summary(by_rating, area_name):
    """Display summary of ratings found."""
    print(f"   Rating distribution for {area_name}:")
    for rating in ['5', '4', '3']:
        count = len(by_rating.get(rating, []))
        stars = '★' * int(rating)
        print(f"      {stars} ({rating}★): {count} establishments")


def export_variety_results(all_results, filename='fsa_variety_results.txt'):
    """Export results organized by rating variety."""
    print(f"\n📄 Exporting to {filename}...")

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("FSA ESTABLISHMENT FINDER - RATING VARIETY\n")
            f.write("=" * 80 + "\n")
            f.write(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            vendor_configs = [
                ('Borough Market Organics', 'SE1', '5'),
                ('Smithfield Premium Meats', 'EC1', '5'),
                ('Spitalfields Artisan Dairy', 'E1', '4'),
                ('Covent Garden Bakery', 'WC2', '4'),
                ('Shoreditch Seafood', 'E2', '3'),
                ('Hackney Provisions', 'E8', 'pending'),
                ('Greenwich Urban Greens', 'SE10', 'pending'),
                ('Brixton Butchers', 'SW9', '3'),
            ]

            f.write("VENDOR CONFIGURATION (Copy into seed_vendors.py):\n")
            f.write("-" * 80 + "\n\n")

            for vendor_name, postcode, target_rating in vendor_configs:
                if target_rating == 'pending':
                    f.write(f"# {vendor_name} - Pending FSA Verification\n")
                    f.write(f"'fsa_establishment_id': None,\n")
                    f.write(f"'fsa_rating_value': None,\n")
                    f.write(f"'fsa_rating_date': None,\n")
                    f.write(f"'fsa_last_checked': None,\n")
                    f.write(f"'fsa_verified': False,\n")
                    f.write(f"# Status: Pending verification\n\n")
                else:
                    area_results = all_results.get(postcode, {})
                    establishments = area_results.get(target_rating, [])

                    if establishments:
                        best = establishments[0]
                        f.write(
                            f"# {vendor_name} - {target_rating}★ FSA Rating\n")
                        f.write(
                            f"'fsa_establishment_id': '{best['fsa_id']}',\n")
                        f.write(
                            f"'fsa_rating_value': None,  # Auto-populates as {target_rating}★\n")
                        f.write(f"'fsa_rating_date': None,  # Auto-populates\n")
                        f.write(f"'fsa_last_checked': None,\n")
                        f.write(
                            f"'fsa_verified': False,  # Will become True after verification\n")
                        f.write(f"# Business: {best['business_name']}\n")
                        f.write(f"# Type: {best['business_type']}\n")
                        f.write(f"# Postcode: {best['postcode']}\n\n")
                    else:
                        f.write(
                            f"# {vendor_name} - No {target_rating}★ found in {postcode}\n")
                        f.write(
                            f"# Use pending state or search different postcode\n")
                        f.write(f"'fsa_establishment_id': None,\n\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write("DETAILED RESULTS BY AREA AND RATING\n")
            f.write("=" * 80 + "\n\n")

            for postcode, by_rating in all_results.items():
                f.write(f"\n{'='*80}\n")
                f.write(f"POSTCODE AREA: {postcode}\n")
                f.write(f"{'='*80}\n")

                for rating in ['5', '4', '3']:
                    establishments = by_rating.get(rating, [])
                    if establishments:
                        f.write(f"\n{rating}★ ESTABLISHMENTS (Top 10):\n")
                        f.write("-" * 80 + "\n")

                        for i, est in enumerate(establishments[:10], 1):
                            f.write(f"\n{i}. FSA ID: {est['fsa_id']}\n")
                            f.write(f"   Name: {est['business_name']}\n")
                            f.write(f"   Type: {est['business_type']}\n")
                            f.write(
                                f"   Address: {est['address_line1']}, {est['postcode']}\n")
                            f.write(f"   Rating Date: {est['rating_date']}\n")
                            f.write(
                                f"   Authority: {est['local_authority']}\n")
                    else:
                        f.write(f"\n{rating}★ ESTABLISHMENTS:\n")
                        f.write("-" * 80 + "\n")
                        f.write(f"   None found in {postcode}\n")

        print(f"   ✓ TXT file created: {filename}")
        return True
    except Exception as e:
        print(f"   ✗ Error creating file: {e}")
        return False


def main():
    """Main function to search for variety of FSA ratings."""
    print("\n" + "=" * 80)
    print("FSA FINDER - RATING VARIETY SEARCH")
    print("=" * 80)
    print("Searching for 3★, 4★, and 5★ establishments across London\n")

    postcode_areas = ['SE1', 'EC1', 'E1', 'WC2', 'E2', 'E8', 'SE10', 'SW9']

    all_results = {}

    for postcode in postcode_areas:
        print(f"\n📍 Searching postcode area: {postcode}")

        data = search_fsa_establishments(postcode, page_size=50)
        by_rating = categorize_by_rating(data)

        if by_rating:
            all_results[postcode] = by_rating
            display_rating_summary(by_rating, postcode)
        else:
            print(f"   ✗ No suitable establishments found")

    if all_results:
        print("\n" + "=" * 80)
        print("EXPORTING RESULTS")
        print("=" * 80)

        success = export_variety_results(all_results)

        if success:
            print("\n" + "=" * 80)
            print("✓ SUCCESS!")
            print("=" * 80)
            print("\nFile created: fsa_variety_results.txt")
            print("\nContents:")
            print("   • Vendor configuration with rating variety")
            print("   • Copy-paste ready code for seed_vendors.py")
            print("   • All establishments organized by rating")
        else:
            print("\n✗ Failed to export results")
    else:
        print("\n✗ No results found in any area")


if __name__ == '__main__':
    try:
        main()
        print("\n✓ Script completed\n")
    except KeyboardInterrupt:
        print("\n\n✗ Script cancelled by user\n")
    except Exception as e:
        print(f"\n\n✗ Unexpected error: {e}\n")
