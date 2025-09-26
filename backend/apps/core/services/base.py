"""
Base service class and utilities for all services.
Provides common functionality like logging, caching, and error handling.
"""
import logging
from typing import Any, Dict, Optional
from django.core.cache import cache
from django.conf import settings


class BaseService:
    """
    Base service class that all other services should inherit from.
    Provides common functionality for logging, caching, and error handling.
    """

    def __init__(self):
        """Initialize the service with a logger."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache_timeout = getattr(settings, 'SERVICE_CACHE_TIMEOUT', 3600)

    def log_info(self, message: str, **kwargs) -> None:
        """
        Log an info message with optional context.

        Args:
            message: The message to log
            **kwargs: Additional context to include in the log
        """
        self.logger.info(message, extra={'context': kwargs})

    def log_error(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """
        Log an error message with optional exception and context.

        Args:
            message: The error message to log
            exception: Optional exception that caused the error
            **kwargs: Additional context to include in the log
        """
        self.logger.error(
            message,
            exc_info=exception,
            extra={'context': kwargs}
        )

    def log_warning(self, message: str, **kwargs) -> None:
        """
        Log a warning message with optional context.

        Args:
            message: The warning message to log
            **kwargs: Additional context to include in the log
        """
        self.logger.warning(message, extra={'context': kwargs})

    def get_from_cache(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.

        Args:
            key: The cache key

        Returns:
            The cached value or None if not found
        """
        try:
            value = cache.get(key)
            if value is not None:
                self.log_info(f"Cache hit for key: {key}")
            return value
        except Exception as e:
            self.log_error(f"Error getting cache key {key}", exception=e)
            return None

    def set_cache(self, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """
        Set a value in cache.

        Args:
            key: The cache key
            value: The value to cache
            timeout: Optional timeout in seconds (defaults to self.cache_timeout)

        Returns:
            True if successful, False otherwise
        """
        try:
            cache.set(key, value, timeout or self.cache_timeout)
            self.log_info(f"Cache set for key: {key}")
            return True
        except Exception as e:
            self.log_error(f"Error setting cache key {key}", exception=e)
            return False

    def delete_from_cache(self, key: str) -> bool:
        """
        Delete a value from cache.

        Args:
            key: The cache key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            cache.delete(key)
            self.log_info(f"Cache deleted for key: {key}")
            return True
        except Exception as e:
            self.log_error(f"Error deleting cache key {key}", exception=e)
            return False

    def build_cache_key(self, prefix: str, *args) -> str:
        """
        Build a cache key from prefix and arguments.

        Args:
            prefix: The cache key prefix
            *args: Additional key components

        Returns:
            The constructed cache key
        """
        components = [str(arg) for arg in args if arg is not None]
        if components:
            return f"{prefix}:{':'.join(components)}"
        return prefix


class ServiceException(Exception):
    """Base exception for service layer errors."""

    def __init__(self, message: str, code: Optional[str] = None, details: Optional[Dict] = None):
        """
        Initialize service exception.

        Args:
            message: Error message
            code: Optional error code for categorization
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ValidationError(ServiceException):
    """Raised when service validation fails."""
    pass


class ExternalServiceError(ServiceException):
    """Raised when an external service (API, Stripe, etc.) fails."""
    pass


class BusinessRuleViolation(ServiceException):
    """Raised when a business rule is violated."""
    pass


class ServiceResult:
    """
    A wrapper for service method results that includes success/failure status.
    Useful for operations that might fail but shouldn't raise exceptions.
    """

    def __init__(self, success: bool, data: Optional[Any] = None,
                 error: Optional[str] = None, error_code: Optional[str] = None):
        """
        Initialize service result.

        Args:
            success: Whether the operation succeeded
            data: The result data if successful
            error: Error message if failed
            error_code: Optional error code for categorization
        """
        self.success = success
        self.data = data
        self.error = error
        self.error_code = error_code

    @classmethod
    def ok(cls, data: Any = None) -> 'ServiceResult':
        """
        Create a successful result.

        Args:
            data: The result data

        Returns:
            A successful ServiceResult instance
        """
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, error_code: Optional[str] = None) -> 'ServiceResult':
        """
        Create a failed result.

        Args:
            error: Error message
            error_code: Optional error code

        Returns:
            A failed ServiceResult instance
        """
        return cls(success=False, error=error, error_code=error_code)

    def __bool__(self) -> bool:
        """Allow ServiceResult to be used in boolean context."""
        return self.success

    def __repr__(self) -> str:
        """String representation of the result."""
        if self.success:
            return f"<ServiceResult: Success, data={self.data}>"
        return f"<ServiceResult: Failure, error={self.error}, code={self.error_code}>"
