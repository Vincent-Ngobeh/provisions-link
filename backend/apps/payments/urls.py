"""
URL configuration for payment endpoints.
"""
from django.urls import path

from .views import (
    CreatePaymentIntentView,
    ConfirmPaymentView,
    PaymentStatusView
)

app_name = 'payments'

urlpatterns = [
    path(
        'create-intent/',
        CreatePaymentIntentView.as_view(),
        name='create-payment-intent'
    ),
    path(
        'confirm-payment/',
        ConfirmPaymentView.as_view(),
        name='confirm-payment'
    ),
    path(
        'payment-status/<str:intent_id>/',
        PaymentStatusView.as_view(),
        name='payment-status'
    ),
]
