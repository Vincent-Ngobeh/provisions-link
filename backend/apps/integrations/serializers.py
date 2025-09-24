from rest_framework import serializers


class StripeAccountLinkSerializer(serializers.Serializer):
    """Response for Stripe Connect onboarding link"""
    url = serializers.URLField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class StripePaymentIntentSerializer(serializers.Serializer):
    """Create payment intent for order/commitment"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    order_id = serializers.IntegerField(required=False)
    group_commitment_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if not attrs.get('order_id') and not attrs.get('group_commitment_id'):
            raise serializers.ValidationError(
                "Either order_id or group_commitment_id is required"
            )
        return attrs


class StripeWebhookSerializer(serializers.Serializer):
    """Process Stripe webhook events"""
    event_type = serializers.CharField()
    event_id = serializers.CharField()
    data = serializers.JSONField()


class PaymentMethodSerializer(serializers.Serializer):
    """Add/update payment method"""
    stripe_payment_method_id = serializers.CharField()
    set_as_default = serializers.BooleanField(default=False)
