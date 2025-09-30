"""
Unit tests for FSAService.
Tests FSA API integration, caching, and vendor rating updates.
"""
from tests.conftest import VendorFactory
import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import requests

from django.utils import timezone
from django.core.cache import cache

from apps.integrations.services.fsa_service import FSAService
from apps.vendors.models import Vendor
from apps.core.services.base import ServiceResult, ExternalServiceError


class TestFSASearch:
    """Test FSA establishment search functionality."""

    def test_search_establishment_success(self, fsa_service):
        """Test successful establishment search."""
        # Arrange
        mock_response = {
            'establishments': [
                {
                    'FHRSID': '12345',
                    'BusinessName': 'Test Restaurant',
                    'BusinessType': 'Restaurant/Cafe/Canteen',
                    'AddressLine1': '123 High Street',
                    'PostCode': 'SW1A 1AA',
                    'RatingValue': '5',
                    'RatingKey': 'fhrs_5_en-gb',
                    'RatingDate': '2024-01-15',
                    'LocalAuthorityName': 'Westminster',
                    'Scores': {
                        'Hygiene': 0,
                        'Structural': 0,
                        'ConfidenceInManagement': 0
                    },
                    'Geocode': {
                        'Latitude': '51.5074',
                        'Longitude': '-0.1276'
                    }
                }
            ]
        }

        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.return_value = mock_response

            # Act
            result = fsa_service.search_establishment(
                business_name='Test Restaurant',
                postcode='SW1A 1AA'
            )

        # Assert
        assert result.success is True
        assert len(result.data) == 1

        establishment = result.data[0]
        assert establishment['fsa_id'] == '12345'
        assert establishment['business_name'] == 'Test Restaurant'
        assert establishment['rating_value'] == 5
        assert establishment['rating_date'] == date(2024, 1, 15)
        assert establishment['address']['postcode'] == 'SW1A 1AA'

    def test_search_establishment_uses_cache(self, fsa_service):
        """Test that search results are cached."""
        # Arrange
        cached_data = [
            {
                'fsa_id': 'CACHED-123',
                'business_name': 'Cached Restaurant',
                'rating_value': 4
            }
        ]

        with patch.object(fsa_service, 'get_from_cache') as mock_cache_get:
            mock_cache_get.return_value = cached_data

            # Act
            result = fsa_service.search_establishment(
                business_name='Cached Restaurant',
                postcode='SW1A 1AA'
            )

        # Assert
        assert result.success is True
        assert result.data == cached_data
        mock_cache_get.assert_called_once()

    def test_search_establishment_no_results(self, fsa_service):
        """Test search with no results."""
        # Arrange
        mock_response = {'establishments': []}

        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.return_value = mock_response

            # Act
            result = fsa_service.search_establishment(
                business_name='Non Existent Restaurant',
                postcode='XX99 9XX'
            )

        # Assert
        assert result.success is False
        assert result.error_code == 'NO_RESULTS'

    def test_search_establishment_handles_api_error(self, fsa_service):
        """Test handling of API errors during search."""
        # Arrange
        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.side_effect = ExternalServiceError('API Error')

            # Act
            result = fsa_service.search_establishment(
                business_name='Test',
                postcode='SW1A 1AA'
            )

        # Assert
        assert result.success is False
        assert result.error_code == 'SEARCH_FAILED'


class TestFSAEstablishmentRetrieval:
    """Test getting specific establishment details."""

    def test_get_establishment_by_id_success(self, fsa_service):
        """Test retrieving establishment by FSA ID."""
        # Arrange
        mock_response = {
            'FHRSID': '12345',
            'BusinessName': 'Test Restaurant',
            'RatingValue': '5',
            'RatingDate': '2024-01-15',
            'Scores': {
                'Hygiene': 5,
                'Structural': 5,
                'ConfidenceInManagement': 10
            }
        }

        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.return_value = mock_response

            # Act
            result = fsa_service.get_establishment_by_id('12345')

        # Assert
        assert result.success is True
        establishment = result.data
        assert establishment['fsa_id'] == '12345'
        assert establishment['rating_value'] == 5
        assert establishment['hygiene_score'] == 5
        assert establishment['structural_score'] == 5
        assert establishment['management_score'] == 10

    def test_get_establishment_not_found(self, fsa_service):
        """Test handling when establishment not found."""
        # Arrange
        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.return_value = None

            # Act
            result = fsa_service.get_establishment_by_id('INVALID-ID')

        # Assert
        assert result.success is False
        assert result.error_code == 'NOT_FOUND'


class TestVendorRatingUpdate:
    """Test updating vendor FSA ratings."""

    @pytest.mark.django_db
    def test_update_vendor_rating_with_fsa_id(self, fsa_service, test_vendor):
        """Test updating vendor rating when FSA ID is known."""
        # Arrange - Clear factory defaults
        test_vendor.fsa_establishment_id = 'FSA-123'
        test_vendor.fsa_rating_value = None  # Clear factory default
        test_vendor.fsa_rating_date = None
        test_vendor.fsa_last_checked = None  # Clear to avoid early return
        test_vendor.save()

        mock_establishment = {
            'fsa_id': 'FSA-123',
            'rating_value': 5,
            'rating_date': date(2024, 1, 15)
        }

        with patch.object(fsa_service, 'get_establishment_by_id') as mock_get:
            mock_get.return_value = ServiceResult.ok(mock_establishment)

            # Act
            result = fsa_service.update_vendor_rating(test_vendor.id)

        # Assert
        assert result.success is True
        assert result.data['rating'] == 5

        test_vendor.refresh_from_db()
        assert test_vendor.fsa_rating_value == 5
        assert test_vendor.fsa_rating_date == date(2024, 1, 15)
        assert test_vendor.fsa_verified is True

    @pytest.mark.django_db
    def test_update_vendor_rating_by_search(self, fsa_service, test_vendor):
        """Test updating vendor rating by searching."""
        # Arrange - Clear factory defaults
        test_vendor.fsa_establishment_id = None
        test_vendor.fsa_rating_value = None  # Clear factory default
        test_vendor.fsa_rating_date = None
        test_vendor.fsa_last_checked = None  # Clear to avoid early return
        test_vendor.save()

        mock_search_result = [
            {
                'fsa_id': 'FOUND-123',
                'business_name': test_vendor.business_name,
                'rating_value': 4,
                'rating_date': date(2024, 1, 10)
            }
        ]

        with patch.object(fsa_service, 'search_establishment') as mock_search:
            mock_search.return_value = ServiceResult.ok(mock_search_result)

            # Act
            result = fsa_service.update_vendor_rating(test_vendor.id)

        # Assert
        assert result.success is True
        assert result.data['rating'] == 4

        test_vendor.refresh_from_db()
        assert test_vendor.fsa_establishment_id == 'FOUND-123'
        assert test_vendor.fsa_rating_value == 4
        assert test_vendor.fsa_verified is True

    @pytest.mark.django_db
    def test_update_vendor_rating_skips_if_recent(self, fsa_service, test_vendor):
        """Test that rating update is skipped if recently checked."""
        # Arrange
        test_vendor.fsa_last_checked = timezone.now() - timedelta(days=3)
        test_vendor.fsa_rating_value = 5
        test_vendor.save()

        # Act
        result = fsa_service.update_vendor_rating(test_vendor.id, force=False)

        # Assert
        assert result.success is True
        assert result.data['message'] == 'Rating recently updated'
        assert result.data['rating'] == 5

    @pytest.mark.django_db
    def test_update_vendor_rating_force_update(self, fsa_service, test_vendor):
        """Test forcing a rating update even if recent."""
        # Arrange - Clear factory defaults
        test_vendor.fsa_last_checked = timezone.now() - timedelta(days=3)
        test_vendor.fsa_establishment_id = 'FSA-123'
        test_vendor.fsa_rating_value = 5  # Current value
        test_vendor.save()

        mock_establishment = {
            'fsa_id': 'FSA-123',
            'rating_value': 3,  # Changed from previous
            'rating_date': date(2024, 1, 20)
        }

        with patch.object(fsa_service, 'get_establishment_by_id') as mock_get:
            mock_get.return_value = ServiceResult.ok(mock_establishment)

            # Act
            result = fsa_service.update_vendor_rating(
                test_vendor.id, force=True)

        # Assert
        assert result.success is True
        assert result.data['rating'] == 3

        test_vendor.refresh_from_db()
        assert test_vendor.fsa_rating_value == 3
        assert test_vendor.fsa_rating_date == date(2024, 1, 20)


class TestFSARatingDistribution:
    """Test area rating distribution analysis."""

    def test_get_rating_distribution(self, fsa_service):
        """Test getting rating distribution for an area."""
        # Arrange
        mock_response = {
            'establishments': [
                {'RatingValue': '5'},
                {'RatingValue': '5'},
                {'RatingValue': '4'},
                {'RatingValue': '3'},
                {'RatingValue': '2'},
                {'RatingValue': '1'},
                {'RatingValue': 'AwaitingInspection'},
                {'RatingValue': 'Exempt'}
            ]
        }

        with patch.object(fsa_service, '_make_request') as mock_request:
            mock_request.return_value = mock_response

            # Act
            result = fsa_service.get_rating_distribution('SW1')

        # Assert
        assert result.success is True
        data = result.data

        assert data['area'] == 'SW1'
        assert data['total_establishments'] == 8
        assert data['total_rated'] == 6  # Excluding awaiting/exempt
        assert data['distribution']['5'] == 2
        assert data['distribution']['4'] == 1
        assert data['distribution']['3'] == 1
        assert data['distribution']['2'] == 1
        assert data['distribution']['1'] == 1
        assert data['distribution']['AwaitingInspection'] == 1
        assert data['distribution']['Exempt'] == 1

        # Average should be (5*2 + 4*1 + 3*1 + 2*1 + 1*1) / 6 = 3.33
        assert abs(data['average_rating'] - 3.33) < 0.1


class TestFSABulkUpdate:
    """Test bulk updating vendor ratings."""

    @pytest.mark.django_db
    def test_bulk_update_all_vendors(self, fsa_service):
        """Test bulk updating all vendors' FSA ratings."""
        # Import Q directly since the FSA service needs it
        from django.db.models import Q

        # Patch the Q import in the FSA service module
        with patch('apps.integrations.services.fsa_service.Q', Q):
            # Create vendors with different update statuses
            vendor_needs_update = VendorFactory(
                fsa_last_checked=timezone.now() - timedelta(days=10)
            )

            vendor_recent = VendorFactory(
                fsa_last_checked=timezone.now() - timedelta(days=3)
            )

            vendor_never_checked = VendorFactory(
                fsa_last_checked=None
            )

            with patch.object(fsa_service, 'update_vendor_rating') as mock_update:
                mock_update.side_effect = [
                    ServiceResult.ok({'rating': 5}),  # vendor_needs_update
                    ServiceResult.ok({'rating': 4}),  # vendor_never_checked
                ]

                # Act
                stats = fsa_service.bulk_update_all_vendors()

            # Assert
            assert stats['total'] == 2  # Only vendors needing update
            assert stats['updated'] == 2
            assert stats['failed'] == 0
            assert mock_update.call_count == 2


class TestFSAHelpers:
    """Test FSA service helper methods."""

    def test_format_establishment_with_numeric_rating(self, fsa_service):
        """Test formatting establishment with numeric rating."""
        # Arrange
        raw_establishment = {
            'FHRSID': '12345',
            'BusinessName': 'Test Restaurant',
            'RatingValue': '4',
            'RatingDate': '2024-01-15T00:00:00',
            'PostCode': 'SW1A 1AA',
            'Scores': {
                'Hygiene': 5,
                'Structural': 5
            }
        }

        # Act
        formatted = fsa_service._format_establishment(raw_establishment)

        # Assert
        assert formatted is not None
        assert formatted['fsa_id'] == '12345'
        assert formatted['rating_value'] == 4  # Converted to int
        assert formatted['rating_date'] == date(2024, 1, 15)

    def test_format_establishment_with_non_numeric_rating(self, fsa_service):
        """Test formatting establishment with non-numeric rating."""
        # Arrange
        raw_establishment = {
            'FHRSID': '12345',
            'BusinessName': 'Test Restaurant',
            'RatingValue': 'AwaitingInspection',
            'RatingDate': '2024-01-15T00:00:00'
        }

        # Act
        formatted = fsa_service._format_establishment(raw_establishment)

        # Assert
        assert formatted is not None
        assert formatted['rating_value'] is None  # Non-numeric becomes None

    def test_make_request_timeout_handling(self, fsa_service):
        """Test handling of request timeouts."""
        # Arrange
        with patch.object(fsa_service.session, 'request') as mock_request:
            mock_request.side_effect = requests.exceptions.Timeout()

            # Act & Assert
            with pytest.raises(ExternalServiceError) as exc_info:
                fsa_service._make_request('GET', '/test')

            assert exc_info.value.code == 'TIMEOUT'

    def test_make_request_error_handling(self, fsa_service):
        """Test handling of request errors."""
        # Arrange
        with patch.object(fsa_service.session, 'request') as mock_request:
            mock_request.side_effect = requests.exceptions.RequestException(
                'Network error')

            # Act & Assert
            with pytest.raises(ExternalServiceError) as exc_info:
                fsa_service._make_request('GET', '/test')

            assert exc_info.value.code == 'API_ERROR'
