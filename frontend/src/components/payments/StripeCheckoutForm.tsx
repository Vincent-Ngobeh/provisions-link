import { useState, FormEvent } from 'react';
import {
  useStripe,
  useElements,
  PaymentElement,
  Elements,
} from '@stripe/react-stripe-js';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, CreditCard, AlertCircle } from 'lucide-react';
import type { Stripe } from '@stripe/stripe-js';

interface StripeCheckoutFormInnerProps {
  onSuccess: (paymentIntentId: string) => void;
  onError: (error: string) => void;
  amount: number;
}

/**
 * Inner form component that uses Stripe hooks
 * Must be wrapped in <Elements> provider
 */
function StripeCheckoutFormInner({
  onSuccess,
  onError,
  amount,
}: StripeCheckoutFormInnerProps) {
  const stripe = useStripe();
  const elements = useElements();
  
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      // Stripe.js hasn't loaded yet
      return;
    }

    setIsProcessing(true);
    setErrorMessage(null);

    try {
      // Confirm payment with Stripe
      const { error, paymentIntent } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/payment-success`,
        },
        redirect: 'if_required', // Don't redirect, handle in-app
      });

      if (error) {
        // Payment failed
        setErrorMessage(error.message || 'Payment failed');
        onError(error.message || 'Payment failed');
      } else if (paymentIntent && paymentIntent.status === 'succeeded') {
        // Payment succeeded
        onSuccess(paymentIntent.id);
      } else {
        // Payment requires additional action
        setErrorMessage('Payment requires additional authentication');
        onError('Payment requires additional authentication');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'An unexpected error occurred');
      onError(err.message || 'An unexpected error occurred');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-5 w-5" />
          Payment Details
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Stripe Payment Element */}
          <div className="p-4 border rounded-lg bg-white">
            <PaymentElement />
          </div>

          {/* Error Message */}
          {errorMessage && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          )}

          {/* Submit Button */}
          <Button
            type="submit"
            className="w-full"
            size="lg"
            disabled={!stripe || isProcessing}
          >
            {isProcessing ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <CreditCard className="h-4 w-4 mr-2" />
                Pay £{(amount / 100).toFixed(2)}
              </>
            )}
          </Button>

          {/* Security Notice */}
          <p className="text-xs text-center text-muted-foreground">
             Secured by Stripe. Your payment information is encrypted.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}

interface StripeCheckoutFormProps extends StripeCheckoutFormInnerProps {
  stripe: Stripe | null;
  clientSecret: string;
}

/**
 * Wrapper component that provides Stripe Elements context
 */
export function StripeCheckoutForm({
  stripe,
  clientSecret,
  onSuccess,
  onError,
  amount,
}: StripeCheckoutFormProps) {
  if (!stripe) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <p>Loading payment form...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const options = {
    clientSecret,
    appearance: {
      theme: 'stripe' as const,
      variables: {
        colorPrimary: '#000000',
      },
    },
  };

  return (
    <Elements stripe={stripe} options={options}>
      <StripeCheckoutFormInner
        onSuccess={onSuccess}
        onError={onError}
        amount={amount}
      />
    </Elements>
  );
}