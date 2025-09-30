"""
Geocoding service for converting UK postcodes to geographic coordinates.
Supports multiple providers with fallback capability.
"""
import requests
import re
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.utils import timezone

from apps.core.services.base import (
    BaseService, ExternalServiceError, ServiceResult, ValidationError
)


class GeocodingService(BaseService):
    """
    Service for geocoding UK postcodes and addresses.
    Provides fallback between multiple providers for reliability.

    Primary: Mapbox (accurate but requires API key)
    Fallback: Nominatim (free but rate limited)
    Cache: PostGIS for previously geocoded postcodes
    """

    # Provider configuration
    MAPBOX_BASE_URL = "https://api.mapbox.com/geocoding/v5"
    NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

    # Cache configuration
    CACHE_PREFIX = "geocode"
    POSTCODE_CACHE_DAYS = 365  # Postcodes don't move!

    # UK Postcode regex pattern
    UK_POSTCODE_PATTERN = r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$'

    # Common UK postcode areas with approximate coordinates (fallback data)
    POSTCODE_AREAS = {
        'SW1': {'lat': 51.4975, 'lng': -0.1357, 'area': 'Westminster'},
        'E1': {'lat': 51.5125, 'lng': -0.0677, 'area': 'Tower Hamlets'},
        'N1': {'lat': 51.5416, 'lng': -0.0968, 'area': 'Islington'},
        'SE1': {'lat': 51.5033, 'lng': -0.0896, 'area': 'Southwark'},
        'W1': {'lat': 51.5142, 'lng': -0.1553, 'area': 'West End'},
        'EC1': {'lat': 51.5246, 'lng': -0.1026, 'area': 'Clerkenwell'},
        'WC1': {'lat': 51.5229, 'lng': -0.1233, 'area': 'Bloomsbury'},
        'NW1': {'lat': 51.5388, 'lng': -0.1426, 'area': 'Camden'},
        'E14': {'lat': 51.5087, 'lng': -0.0199, 'area': 'Canary Wharf'},
        'SW3': {'lat': 51.4893, 'lng': -0.1641, 'area': 'Chelsea'},
    }

    def __init__(self):
        """Initialize geocoding service with session for connection pooling."""
        super().__init__()
        self.session = requests.Session()
        self.mapbox_token = getattr(settings, 'MAPBOX_API_TOKEN', None)
        self.use_mapbox = bool(self.mapbox_token)

        # Set user agent for Nominatim (required)
        self.session.headers.update({
            'User-Agent': 'ProvisionsLink/1.0 (B2B Marketplace)'
        })

    def geocode_postcode(self, postcode: str) -> ServiceResult:
        """
        Convert a UK postcode to geographic coordinates.

        Args:
            postcode: UK postcode (e.g., 'SW1A 1AA')

        Returns:
            ServiceResult containing Point and area information or error
        """
        try:
            # Normalize postcode
            postcode = self.normalize_postcode(postcode)

            if not postcode:
                return ServiceResult.fail(
                    "Invalid UK postcode format",
                    error_code="INVALID_POSTCODE"
                )

            # Check cache first
            cached_result = self._get_cached_location(postcode)
            if cached_result:
                return ServiceResult.ok(cached_result)

            # Try primary provider (Mapbox if configured)
            if self.use_mapbox:
                result = self._geocode_with_mapbox(postcode)
                if result.success:
                    self._cache_location(postcode, result.data)
                    return result

            # Fallback to Nominatim
            result = self._geocode_with_nominatim(postcode)
            if result.success:
                self._cache_location(postcode, result.data)
                return result

            # Last resort: Use approximate area coordinates
            area_result = self._get_approximate_location(postcode)
            if area_result:
                self.log_warning(
                    f"Using approximate location for {postcode}",
                    postcode=postcode
                )
                return ServiceResult.ok(area_result)

            return ServiceResult.fail(
                f"Could not geocode postcode {postcode}",
                error_code="GEOCODING_FAILED"
            )

        except Exception as e:
            self.log_error(
                f"Error geocoding postcode",
                exception=e,
                postcode=postcode
            )
            return ServiceResult.fail(
                "Geocoding failed",
                error_code="GEOCODING_ERROR"
            )

    def geocode_address(self, address: str, postcode: Optional[str] = None) -> ServiceResult:
        """
        Geocode a full address.

        Args:
            address: Address string
            postcode: Optional postcode to improve accuracy

        Returns:
            ServiceResult containing Point and formatted address or error
        """
        try:
            # Build full address string
            if postcode:
                full_address = f"{address}, {postcode}, United Kingdom"
            else:
                full_address = f"{address}, United Kingdom"

            # Try Mapbox first if available
            if self.use_mapbox:
                result = self._geocode_address_with_mapbox(full_address)
                if result.success:
                    return result

            # Fallback to Nominatim
            result = self._geocode_address_with_nominatim(full_address)
            if result.success:
                return result

            # If we have a postcode, try geocoding just that
            if postcode:
                return self.geocode_postcode(postcode)

            return ServiceResult.fail(
                "Could not geocode address",
                error_code="GEOCODING_FAILED"
            )

        except Exception as e:
            self.log_error(
                f"Error geocoding address",
                exception=e,
                address=address
            )
            return ServiceResult.fail(
                "Address geocoding failed",
                error_code="GEOCODING_ERROR"
            )

    def reverse_geocode(self, point: Point) -> ServiceResult:
        """
        Convert coordinates to an address (reverse geocoding).

        Args:
            point: Point object with coordinates

        Returns:
            ServiceResult containing address information or error
        """
        try:
            # Try Mapbox first if available
            if self.use_mapbox:
                result = self._reverse_geocode_with_mapbox(point)
                if result.success:
                    return result

            # Fallback to Nominatim
            return self._reverse_geocode_with_nominatim(point)

        except Exception as e:
            self.log_error(
                f"Error reverse geocoding",
                exception=e,
                lat=point.y,
                lng=point.x
            )
            return ServiceResult.fail(
                "Reverse geocoding failed",
                error_code="REVERSE_GEOCODING_ERROR"
            )

    def calculate_distance(
        self,
        point1: Point,
        point2: Point
    ) -> Decimal:
        """
        Calculate distance between two points in kilometers.

        Args:
            point1: First Point
            point2: Second Point

        Returns:
            Distance in kilometers as Decimal
        """
        try:
            # Calculate using geodesic distance (haversine formula already implemented in models)
            # Point.distance() returns degrees for SRID 4326, convert to km
            from math import radians, cos, sin, sqrt, atan2

            lat1, lon1 = radians(point1.y), radians(point1.x)
            lat2, lon2 = radians(point2.y), radians(point2.x)

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            distance_km = 6371 * c  # Earth radius in km

            return Decimal(str(distance_km))

        except Exception as e:
            self.log_error(f"Error calculating distance", exception=e)
            return Decimal('0')

    def find_nearby_postcodes(
        self,
        center_postcode: str,
        radius_km: int = 5
    ) -> ServiceResult:
        """
        Find postcodes within a radius of a center postcode.

        Args:
            center_postcode: Center postcode
            radius_km: Search radius in kilometers

        Returns:
            ServiceResult containing list of nearby postcodes or error
        """
        try:
            # Geocode center postcode
            center_result = self.geocode_postcode(center_postcode)

            if not center_result.success:
                return center_result

            center_point = center_result.data['point']

            # This would query a postcode database
            # For now, return approximate result based on known areas
            nearby = []

            for area_code, area_data in self.POSTCODE_AREAS.items():
                area_point = Point(area_data['lng'], area_data['lat'])
                distance = self.calculate_distance(center_point, area_point)

                if distance <= radius_km:
                    nearby.append({
                        'postcode': area_code,
                        'area': area_data['area'],
                        'distance_km': float(distance)
                    })

            # Sort by distance
            nearby.sort(key=lambda x: x['distance_km'])

            return ServiceResult.ok(nearby)

        except Exception as e:
            self.log_error(
                f"Error finding nearby postcodes",
                exception=e,
                center=center_postcode
            )
            return ServiceResult.fail(
                "Failed to find nearby postcodes",
                error_code="SEARCH_FAILED"
            )

    def validate_delivery_radius(
        self,
        vendor_location: Point,
        delivery_location: Point,
        max_radius_km: int
    ) -> bool:
        """
        Check if delivery location is within vendor's radius.

        Args:
            vendor_location: Vendor's location point
            delivery_location: Delivery location point
            max_radius_km: Maximum delivery radius

        Returns:
            True if within radius, False otherwise
        """
        try:
            distance = self.calculate_distance(
                vendor_location, delivery_location)
            return distance <= max_radius_km
        except Exception:
            return False

    def normalize_postcode(self, postcode: str) -> Optional[str]:
        """
        Normalize and validate UK postcode format.

        Args:
            postcode: Raw postcode string

        Returns:
            Normalized postcode or None if invalid
        """
        if not postcode:
            return None

        # Remove spaces and convert to uppercase
        normalized = postcode.upper().strip()

        # Add space before last 3 characters if missing
        if len(normalized) >= 5 and ' ' not in normalized:
            normalized = normalized[:-3] + ' ' + normalized[-3:]

        # Validate format
        if not re.match(self.UK_POSTCODE_PATTERN, normalized):
            return None

        return normalized

    def get_postcode_area(self, postcode: str) -> str:
        """
        Extract area code from postcode (e.g., 'SW1' from 'SW1A 1AA').

        Args:
            postcode: Full postcode

        Returns:
            Area code
        """
        normalized = self.normalize_postcode(postcode)
        if not normalized:
            return ""

        # Extract area (first part before the digit that follows a letter)
        match = re.match(r'^([A-Z]{1,2}\d{1,2})', normalized)
        if match:
            return match.group(1)

        return ""

    def _geocode_with_mapbox(self, postcode: str) -> ServiceResult:
        """
        Geocode using Mapbox API.

        Args:
            postcode: Normalized UK postcode

        Returns:
            ServiceResult with geocoding data
        """
        try:
            url = f"{self.MAPBOX_BASE_URL}/mapbox.places/{postcode}.json"

            params = {
                'access_token': self.mapbox_token,
                'country': 'GB',
                'types': 'postcode',
                'limit': 1
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data.get('features'):
                feature = data['features'][0]
                coordinates = feature['geometry']['coordinates']

                return ServiceResult.ok({
                    'point': Point(coordinates[0], coordinates[1]),
                    'lng': coordinates[0],
                    'lat': coordinates[1],
                    'area_name': feature.get('place_name', postcode),
                    'confidence': feature.get('relevance', 1.0),
                    'provider': 'mapbox'
                })

            return ServiceResult.fail(
                "No results from Mapbox",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Mapbox API error",
                exception=e,
                postcode=postcode
            )
            return ServiceResult.fail(
                "Mapbox geocoding failed",
                error_code="API_ERROR"
            )

    def _geocode_with_nominatim(self, postcode: str) -> ServiceResult:
        """
        Geocode using Nominatim (OpenStreetMap).

        Args:
            postcode: Normalized UK postcode

        Returns:
            ServiceResult with geocoding data
        """
        try:
            url = f"{self.NOMINATIM_BASE_URL}/search"

            params = {
                'q': f"{postcode}, United Kingdom",
                'format': 'json',
                'limit': 1,
                'addressdetails': 1,
                'countrycodes': 'gb'
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data:
                result = data[0]
                lat = float(result['lat'])
                lng = float(result['lon'])

                return ServiceResult.ok({
                    'point': Point(lng, lat),
                    'lng': lng,
                    'lat': lat,
                    'area_name': result.get('display_name', postcode).split(',')[0],
                    'confidence': float(result.get('importance', 0.5)),
                    'provider': 'nominatim'
                })

            return ServiceResult.fail(
                "No results from Nominatim",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Nominatim API error",
                exception=e,
                postcode=postcode
            )
            return ServiceResult.fail(
                "Nominatim geocoding failed",
                error_code="API_ERROR"
            )

    def _geocode_address_with_mapbox(self, address: str) -> ServiceResult:
        """
        Geocode full address using Mapbox.

        Args:
            address: Full address string

        Returns:
            ServiceResult with geocoding data
        """
        try:
            url = f"{self.MAPBOX_BASE_URL}/mapbox.places/{address}.json"

            params = {
                'access_token': self.mapbox_token,
                'country': 'GB',
                'limit': 1
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data.get('features'):
                feature = data['features'][0]
                coordinates = feature['geometry']['coordinates']

                # Extract postcode from context
                postcode = None
                for context in feature.get('context', []):
                    if 'postcode' in context.get('id', ''):
                        postcode = context.get('text')
                        break

                return ServiceResult.ok({
                    'point': Point(coordinates[0], coordinates[1]),
                    'lng': coordinates[0],
                    'lat': coordinates[1],
                    'formatted_address': feature.get('place_name', address),
                    'postcode': postcode,
                    'confidence': feature.get('relevance', 1.0),
                    'provider': 'mapbox'
                })

            return ServiceResult.fail(
                "No results from Mapbox",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Mapbox address geocoding error",
                exception=e
            )
            return ServiceResult.fail(
                "Mapbox geocoding failed",
                error_code="API_ERROR"
            )

    def _geocode_address_with_nominatim(self, address: str) -> ServiceResult:
        """
        Geocode full address using Nominatim.

        Args:
            address: Full address string

        Returns:
            ServiceResult with geocoding data
        """
        try:
            url = f"{self.NOMINATIM_BASE_URL}/search"

            params = {
                'q': address,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1,
                'countrycodes': 'gb'
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data:
                result = data[0]
                lat = float(result['lat'])
                lng = float(result['lon'])

                address_parts = result.get('address', {})

                return ServiceResult.ok({
                    'point': Point(lng, lat),
                    'lng': lng,
                    'lat': lat,
                    'formatted_address': result.get('display_name', address),
                    'postcode': address_parts.get('postcode'),
                    'confidence': float(result.get('importance', 0.5)),
                    'provider': 'nominatim'
                })

            return ServiceResult.fail(
                "No results from Nominatim",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Nominatim address geocoding error",
                exception=e
            )
            return ServiceResult.fail(
                "Nominatim geocoding failed",
                error_code="API_ERROR"
            )

    def _reverse_geocode_with_mapbox(self, point: Point) -> ServiceResult:
        """
        Reverse geocode using Mapbox.

        Args:
            point: Point with coordinates

        Returns:
            ServiceResult with address data
        """
        try:
            url = f"{self.MAPBOX_BASE_URL}/mapbox.places/{point.x},{point.y}.json"

            params = {
                'access_token': self.mapbox_token,
                'country': 'GB',
                'types': 'postcode,address'
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data.get('features'):
                feature = data['features'][0]

                return ServiceResult.ok({
                    'formatted_address': feature.get('place_name', ''),
                    'postcode': feature.get('text', ''),
                    'provider': 'mapbox'
                })

            return ServiceResult.fail(
                "No results from Mapbox reverse geocoding",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Mapbox reverse geocoding error",
                exception=e
            )
            return ServiceResult.fail(
                "Mapbox reverse geocoding failed",
                error_code="API_ERROR"
            )

    def _reverse_geocode_with_nominatim(self, point: Point) -> ServiceResult:
        """
        Reverse geocode using Nominatim.

        Args:
            point: Point with coordinates

        Returns:
            ServiceResult with address data
        """
        try:
            url = f"{self.NOMINATIM_BASE_URL}/reverse"

            params = {
                'lat': point.y,
                'lon': point.x,
                'format': 'json',
                'addressdetails': 1,
                'zoom': 18
            }

            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data:
                address_parts = data.get('address', {})

                return ServiceResult.ok({
                    'formatted_address': data.get('display_name', ''),
                    'postcode': address_parts.get('postcode', ''),
                    'provider': 'nominatim'
                })

            return ServiceResult.fail(
                "No results from Nominatim reverse geocoding",
                error_code="NO_RESULTS"
            )

        except requests.RequestException as e:
            self.log_error(
                f"Nominatim reverse geocoding error",
                exception=e
            )
            return ServiceResult.fail(
                "Nominatim reverse geocoding failed",
                error_code="API_ERROR"
            )

    def _get_approximate_location(self, postcode: str) -> Optional[Dict]:
        """
        Get approximate location from postcode area.

        Args:
            postcode: UK postcode

        Returns:
            Location data or None
        """
        area = self.get_postcode_area(postcode)

        if area in self.POSTCODE_AREAS:
            area_data = self.POSTCODE_AREAS[area]
            return {
                'point': Point(area_data['lng'], area_data['lat']),
                'lng': area_data['lng'],
                'lat': area_data['lat'],
                'area_name': area_data['area'],
                'confidence': 0.3,  # Low confidence for approximate
                'provider': 'approximate'
            }

        return None

    def _get_cached_location(self, postcode: str) -> Optional[Dict]:
        """
        Get cached location for postcode.

        Args:
            postcode: Normalized postcode

        Returns:
            Cached location data or None
        """
        cache_key = self.build_cache_key(self.CACHE_PREFIX, postcode)
        return self.get_from_cache(cache_key)

    def _cache_location(self, postcode: str, location_data: Dict) -> None:
        """
        Cache location data for postcode.

        Args:
            postcode: Normalized postcode
            location_data: Location data to cache
        """
        cache_key = self.build_cache_key(self.CACHE_PREFIX, postcode)
        cache_timeout = self.POSTCODE_CACHE_DAYS * 86400
        self.set_cache(cache_key, location_data, timeout=cache_timeout)
