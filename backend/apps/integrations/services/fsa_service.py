"""
FSA (Food Standards Agency) API integration service.
Handles fetching and caching food hygiene ratings for UK establishments.
"""
import requests
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone
from django.conf import settings
from django.db import models
from django.db.models import Q
from celery import shared_task

from apps.core.services.base import (
    BaseService, ExternalServiceError, ServiceResult
)
from apps.vendors.models import Vendor


class FSAService(BaseService):
    """
    Service for interacting with the FSA (Food Standards Agency) API.
    Fetches and manages food hygiene ratings for vendors.

    API Documentation: https://api.ratings.food.gov.uk/help
    """

    # API Configuration
    BASE_URL = "https://api.ratings.food.gov.uk"
    API_VERSION = "2"

    # Cache configuration
    CACHE_PREFIX = "fsa"
    ESTABLISHMENT_CACHE_DAYS = 7
    SEARCH_CACHE_HOURS = 24

    # Rate limiting (FSA API has generous limits but we should be respectful)
    MAX_REQUESTS_PER_SECOND = 10

    def __init__(self):
        """Initialize FSA service with session for connection pooling."""
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            'x-api-version': self.API_VERSION,
            'Accept': 'application/json'
        })

    def _sanitize_cache_key(self, key: str) -> str:
        """
        Sanitize cache key to remove characters that cause issues with memcached.

        Args:
            key: Original cache key

        Returns:
            Sanitized cache key with spaces and special chars replaced
        """
        # Replace spaces with underscores and remove any other problematic characters
        # Memcached doesn't allow spaces, newlines, carriage returns, or null bytes
        sanitized = key.replace(' ', '_')
        sanitized = re.sub(r'[\r\n\x00]', '', sanitized)
        return sanitized

    def _is_test_fsa_id(self, fsa_id: str) -> bool:
        """
        Check if an FSA ID is a test/dummy ID.

        Args:
            fsa_id: FSA establishment ID

        Returns:
            True if this appears to be a test ID
        """
        if not fsa_id:
            return True

        # Common test patterns
        test_patterns = [
            r'^FSA-TEST',
            r'^TEST',
            r'^DUMMY',
            r'^EXAMPLE',
            r'^000000',
            r'^999999'
        ]

        fsa_id_upper = fsa_id.upper()
        return any(re.match(pattern, fsa_id_upper) for pattern in test_patterns)

    def search_establishment(
        self,
        business_name: str,
        postcode: str,
        max_results: int = 5
    ) -> ServiceResult:
        """
        Search for an establishment by name and postcode.

        Args:
            business_name: Name of the business
            postcode: UK postcode
            max_results: Maximum number of results to return

        Returns:
            ServiceResult containing list of matching establishments or error
        """
        try:
            # Check cache first - sanitize the cache key
            cache_key = self.build_cache_key(
                self.CACHE_PREFIX,
                'search',
                business_name.lower().replace(' ', '_'),
                postcode.upper()
            )
            cache_key = self._sanitize_cache_key(cache_key)

            cached_result = self.get_from_cache(cache_key)
            if cached_result:
                return ServiceResult.ok(cached_result)

            # Prepare API request
            params = {
                'name': business_name,
                'address': postcode,
                'pageSize': max_results,
                'pageNumber': 1
            }

            # Make API request
            response = self._make_request(
                'GET', '/Establishments', params=params)

            if not response:
                return ServiceResult.fail(
                    "Failed to connect to FSA API",
                    error_code="API_CONNECTION_FAILED"
                )

            # Parse response
            establishments = response.get('establishments', [])

            if not establishments:
                return ServiceResult.fail(
                    f"No establishments found for {business_name} in {postcode}",
                    error_code="NO_RESULTS"
                )

            # Format results
            results = []
            for establishment in establishments[:max_results]:
                formatted = self._format_establishment(establishment)
                if formatted:
                    results.append(formatted)

            # Cache results
            cache_timeout = int(self.SEARCH_CACHE_HOURS * 3600)
            self.set_cache(cache_key, results, timeout=cache_timeout)

            self.log_info(
                f"Found {len(results)} establishments for {business_name}",
                business_name=business_name,
                postcode=postcode
            )

            return ServiceResult.ok(results)

        except Exception as e:
            self.log_error(
                f"Error searching establishments",
                exception=e,
                business_name=business_name,
                postcode=postcode
            )
            return ServiceResult.fail(
                "Failed to search establishments",
                error_code="SEARCH_FAILED"
            )

    def get_establishment_by_id(self, fsa_id: str) -> ServiceResult:
        """
        Get detailed information about a specific establishment.

        Args:
            fsa_id: FSA establishment ID (FHRSID)

        Returns:
            ServiceResult containing establishment details or error
        """
        try:
            # Check if this is a test/dummy FSA ID
            if self._is_test_fsa_id(fsa_id):
                self.log_info(
                    f"Skipping test FSA ID: {fsa_id}",
                    fsa_id=fsa_id
                )
                return ServiceResult.fail(
                    f"FSA ID {fsa_id} appears to be a test/dummy ID",
                    error_code="INVALID_TEST_ID"
                )

            # Check cache
            cache_key = self.build_cache_key(
                self.CACHE_PREFIX, 'establishment', fsa_id)
            cache_key = self._sanitize_cache_key(cache_key)
            cached_result = self.get_from_cache(cache_key)

            if cached_result:
                return ServiceResult.ok(cached_result)

            # Make API request
            response = self._make_request('GET', f'/Establishments/{fsa_id}')

            if not response:
                return ServiceResult.fail(
                    f"Establishment {fsa_id} not found",
                    error_code="NOT_FOUND"
                )

            # Format establishment data
            formatted = self._format_establishment(response)

            if not formatted:
                return ServiceResult.fail(
                    "Invalid establishment data",
                    error_code="INVALID_DATA"
                )

            # Cache for longer as specific lookups are less likely to change
            cache_timeout = int(self.ESTABLISHMENT_CACHE_DAYS * 86400)
            self.set_cache(cache_key, formatted, timeout=cache_timeout)

            return ServiceResult.ok(formatted)

        except ExternalServiceError as e:
            # Handle API errors gracefully
            self.log_error(
                f"Error fetching establishment {fsa_id}",
                exception=e
            )

            # If it's a 400 error, likely an invalid FSA ID
            if "400" in str(e):
                return ServiceResult.fail(
                    f"Invalid FSA ID: {fsa_id}",
                    error_code="INVALID_FSA_ID"
                )

            return ServiceResult.fail(
                "Failed to fetch establishment",
                error_code="FETCH_FAILED"
            )
        except Exception as e:
            self.log_error(
                f"Error fetching establishment {fsa_id}",
                exception=e
            )
            return ServiceResult.fail(
                "Failed to fetch establishment",
                error_code="FETCH_FAILED"
            )

    def update_vendor_rating(self, vendor_id: int, force: bool = False) -> ServiceResult:
        """
        Update a vendor's FSA rating.

        Args:
            vendor_id: ID of the vendor to update
            force: Force update even if recently checked

        Returns:
            ServiceResult containing updated rating or error
        """
        try:
            vendor = Vendor.objects.get(id=vendor_id)

            # Check if update is needed
            if not force and vendor.fsa_last_checked:
                days_since_check = (
                    timezone.now() - vendor.fsa_last_checked).days
                if days_since_check < 7:
                    return ServiceResult.ok({
                        'message': 'Rating recently updated',
                        'rating': vendor.fsa_rating_value,
                        'last_checked': vendor.fsa_last_checked
                    })

            # If we have an FSA ID, fetch directly
            if vendor.fsa_establishment_id:
                result = self.get_establishment_by_id(
                    vendor.fsa_establishment_id)

                if result.success:
                    establishment = result.data
                    vendor.fsa_rating_value = establishment['rating_value']
                    vendor.fsa_rating_date = establishment['rating_date']
                    vendor.fsa_last_checked = timezone.now()
                    vendor.fsa_verified = True
                    vendor.save(update_fields=[
                        'fsa_rating_value',
                        'fsa_rating_date',
                        'fsa_last_checked',
                        'fsa_verified'
                    ])

                    return ServiceResult.ok({
                        'rating': establishment['rating_value'],
                        'rating_date': establishment['rating_date'],
                        'updated': True
                    })
                else:
                    # If FSA ID is invalid/test, mark as unverified and update last checked
                    if result.error_code in ['INVALID_TEST_ID', 'INVALID_FSA_ID', 'NOT_FOUND']:
                        vendor.fsa_verified = False
                        vendor.fsa_last_checked = timezone.now()
                        vendor.save(update_fields=[
                                    'fsa_verified', 'fsa_last_checked'])

                        self.log_info(
                            f"Vendor {vendor_id} has invalid FSA ID: {vendor.fsa_establishment_id}",
                            vendor_id=vendor_id,
                            fsa_id=vendor.fsa_establishment_id
                        )

                        return ServiceResult.fail(
                            f"Invalid FSA ID for vendor: {result.error}",
                            error_code=result.error_code
                        )

            # Try searching by name and postcode
            if vendor.business_name and vendor.postcode:
                result = self.search_establishment(
                    business_name=vendor.business_name,
                    postcode=vendor.postcode,
                    max_results=3
                )

                if result.success and result.data:
                    # Use the first (best) match
                    establishment = result.data[0]

                    # Update vendor with FSA data
                    vendor.fsa_establishment_id = establishment['fsa_id']
                    vendor.fsa_rating_value = establishment['rating_value']
                    vendor.fsa_rating_date = establishment['rating_date']
                    vendor.fsa_last_checked = timezone.now()
                    vendor.fsa_verified = True
                    vendor.save(update_fields=[
                        'fsa_establishment_id',
                        'fsa_rating_value',
                        'fsa_rating_date',
                        'fsa_last_checked',
                        'fsa_verified'
                    ])

                    return ServiceResult.ok({
                        'rating': establishment['rating_value'],
                        'rating_date': establishment['rating_date'],
                        'updated': True,
                        'newly_linked': True
                    })

            # No FSA data found
            vendor.fsa_last_checked = timezone.now()
            vendor.fsa_verified = False
            vendor.save(update_fields=['fsa_last_checked', 'fsa_verified'])

            return ServiceResult.fail(
                "No FSA establishment found for vendor",
                error_code="NO_MATCH"
            )

        except Vendor.DoesNotExist:
            return ServiceResult.fail(
                f"Vendor {vendor_id} not found",
                error_code="VENDOR_NOT_FOUND"
            )
        except Exception as e:
            self.log_error(
                f"Error updating vendor rating",
                exception=e,
                vendor_id=vendor_id
            )
            return ServiceResult.fail(
                "Failed to update vendor rating",
                error_code="UPDATE_FAILED"
            )

    def get_rating_distribution(self, postcode_area: str) -> ServiceResult:
        """
        Get the distribution of ratings for a postcode area.

        Args:
            postcode_area: UK postcode area (e.g., 'SW1A', 'E1')

        Returns:
            ServiceResult containing rating statistics
        """
        try:
            # Sanitize cache key
            cache_key = self.build_cache_key(
                self.CACHE_PREFIX, 'distribution', postcode_area)
            cache_key = self._sanitize_cache_key(cache_key)

            cached_result = self.get_from_cache(cache_key)
            if cached_result:
                return ServiceResult.ok(cached_result)

            # Search for establishments in this area
            params = {
                'address': postcode_area,
                'pageSize': 500,
                'pageNumber': 1
            }

            response = self._make_request(
                'GET', '/Establishments', params=params)

            if not response:
                return ServiceResult.fail(
                    "Failed to fetch establishments",
                    error_code="API_ERROR"
                )

            establishments = response.get('establishments', [])

            # Calculate distribution
            distribution = {
                '5': 0,
                '4': 0,
                '3': 0,
                '2': 0,
                '1': 0,
                '0': 0,
                'AwaitingInspection': 0,
                'Exempt': 0
            }

            total_rated = 0

            for est in establishments:
                rating = est.get('RatingValue', 'Unknown')
                if rating in distribution:
                    distribution[rating] += 1
                    if rating.isdigit():
                        total_rated += 1

            # Calculate average
            weighted_sum = sum(
                int(rating) * count
                for rating, count in distribution.items()
                if rating.isdigit()
            )

            average_rating = weighted_sum / total_rated if total_rated > 0 else 0

            result_data = {
                'area': postcode_area,
                'total_establishments': len(establishments),
                'total_rated': total_rated,
                'average_rating': round(average_rating, 2),
                'distribution': distribution
            }

            # Cache for 24 hours
            cache_timeout = int(self.SEARCH_CACHE_HOURS * 3600)
            self.set_cache(cache_key, result_data, timeout=cache_timeout)

            return ServiceResult.ok(result_data)

        except Exception as e:
            self.log_error(
                f"Error fetching rating distribution",
                exception=e,
                area=postcode_area
            )
            return ServiceResult.fail(
                "Failed to fetch distribution",
                error_code="FETCH_FAILED"
            )

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        timeout: int = 10
    ) -> Optional[Dict]:
        """
        Make a request to the FSA API.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            Response data or None if failed
        """
        try:
            url = f"{self.BASE_URL}{endpoint}"

            response = self.session.request(
                method=method,
                url=url,
                params=params,
                timeout=timeout
            )

            response.raise_for_status()

            # FSA API returns JSON
            return response.json()

        except requests.exceptions.HTTPError as e:
            # Log HTTP errors but raise them for proper handling upstream
            self.log_error(
                f"FSA API HTTP error for {endpoint}: {e.response.status_code}")
            raise ExternalServiceError(
                f"FSA API error: {str(e)}",
                code=f"HTTP_{e.response.status_code}"
            )
        except requests.exceptions.Timeout:
            self.log_error(f"FSA API timeout for {endpoint}")
            raise ExternalServiceError("FSA API timeout", code="TIMEOUT")
        except requests.exceptions.RequestException as e:
            self.log_error(f"FSA API request failed", exception=e)
            raise ExternalServiceError(
                f"FSA API error: {str(e)}",
                code="API_ERROR"
            )
        except ValueError as e:
            self.log_error(f"Invalid JSON response from FSA API", exception=e)
            return None

    def _format_establishment(self, establishment: Dict) -> Optional[Dict[str, Any]]:
        """
        Format raw FSA establishment data into our standard format.

        Args:
            establishment: Raw establishment data from FSA API

        Returns:
            Formatted establishment dict or None if invalid
        """
        try:
            # Parse rating value
            rating_value = establishment.get('RatingValue', '')

            # Convert to integer if numeric, otherwise None
            if rating_value.isdigit():
                rating_value = int(rating_value)
            else:
                rating_value = None  # For 'AwaitingInspection', 'Exempt', etc.

            # Parse rating date
            rating_date_str = establishment.get('RatingDate', '')
            rating_date = None

            if rating_date_str:
                try:
                    rating_date = datetime.strptime(
                        rating_date_str.split('T')[0],
                        '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass

            return {
                'fsa_id': establishment.get('FHRSID', ''),
                'business_name': establishment.get('BusinessName', ''),
                'business_type': establishment.get('BusinessType', ''),
                'address': {
                    'line1': establishment.get('AddressLine1', ''),
                    'line2': establishment.get('AddressLine2', ''),
                    'line3': establishment.get('AddressLine3', ''),
                    'line4': establishment.get('AddressLine4', ''),
                    'postcode': establishment.get('PostCode', '')
                },
                'rating_value': rating_value,
                'rating_key': establishment.get('RatingKey', ''),
                'rating_date': rating_date,
                'local_authority': establishment.get('LocalAuthorityName', ''),
                'hygiene_score': establishment.get('Scores', {}).get('Hygiene'),
                'structural_score': establishment.get('Scores', {}).get('Structural'),
                'management_score': establishment.get('Scores', {}).get('ConfidenceInManagement'),
                'scheme_type': establishment.get('SchemeType', ''),
                'geocode': {
                    'latitude': establishment.get('Geocode', {}).get('Latitude'),
                    'longitude': establishment.get('Geocode', {}).get('Longitude')
                }
            }
        except Exception as e:
            self.log_error(
                f"Error formatting establishment data",
                exception=e
            )
            return None

    def bulk_update_all_vendors(self) -> Dict[str, int]:
        """
        Update all vendors' FSA ratings (for periodic task).

        Returns:
            Statistics about the update process
        """
        stats = {
            'total': 0,
            'updated': 0,
            'failed': 0,
            'skipped': 0
        }

        # Get all vendors that need updating (not checked in last 7 days)
        cutoff_date = timezone.now() - timedelta(days=7)
        vendors = Vendor.objects.filter(
            Q(fsa_last_checked__isnull=True) |
            Q(fsa_last_checked__lt=cutoff_date)
        )

        stats['total'] = vendors.count()

        for vendor in vendors:
            result = self.update_vendor_rating(vendor.id)
            if result.success:
                stats['updated'] += 1
            else:
                if result.error_code in ['NO_MATCH', 'INVALID_TEST_ID', 'INVALID_FSA_ID']:
                    stats['skipped'] += 1
                else:
                    stats['failed'] += 1

        self.log_info(
            "Bulk FSA update completed",
            stats=stats
        )

        return stats


# Celery tasks that use the FSA service

@shared_task(name='update_vendor_fsa_rating')
def update_vendor_fsa_rating(vendor_id: int) -> Dict[str, Any]:
    """
    Celery task to update a single vendor's FSA rating.

    Args:
        vendor_id: ID of the vendor to update

    Returns:
        Result of the update operation
    """
    service = FSAService()
    result = service.update_vendor_rating(vendor_id)

    if result.success:
        return {
            'success': True,
            'data': result.data
        }
    else:
        return {
            'success': False,
            'error': result.error,
            'error_code': result.error_code
        }


@shared_task(name='bulk_update_fsa_ratings')
def bulk_update_fsa_ratings() -> Dict[str, int]:
    """
    Celery periodic task to update all vendors' FSA ratings.
    Should be scheduled to run weekly.

    Returns:
        Statistics about the update process
    """
    service = FSAService()
    return service.bulk_update_all_vendors()
