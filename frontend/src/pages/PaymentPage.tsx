import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { paymentsApi } from '@/api/paymentsApi';
import { getStripe } from '@/lib/stripe';
import { StripeCheckoutForm } from '@/components/payments/StripeCheckoutForm';
import { PaymentSummary } from '@/components/payments/PaymentSummary';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  ArrowLeft,
  CheckCircle,
  Loader2,
  AlertCircle,
  CreditCard,
} from 'lucide-react';
import type { Stripe } from '@stripe/stripe-js';

export default function PaymentPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams] = useSearchParams();
  
  const [stripe, setStripe] = useState<Stripe | null>(null);
  const [showSuccessDialog, setShowSuccessDialog] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  // Get order IDs from URL params
  const orderIdsParam = searchParams.get('orderIds');
  const orderIds = orderIdsParam
    ? orderIdsParam.split(',').map(Number)
    : [];

  // Redirect if no order IDs
  useEffect(() => {
    if (orderIds.length === 0) {
      toast({
        title: 'No Orders',
        description: 'No orders found for payment',
        variant: 'destructive',
      });
      navigate('/cart');
    }
  }, [orderIds, navigate, toast]);

  // Load Stripe
  useEffect(() => {
    getStripe().then(setStripe);
  }, []);

  // Create payment intent
  const {
    data: paymentIntentData,
    isLoading: isLoadingIntent,
    error: intentError,
  } = useQuery({
    queryKey: ['payment-intent', orderIds],
    queryFn: () => paymentsApi.createIntent(orderIds),
    enabled: orderIds.length > 0,
    retry: 1,
  });

  const paymentIntent = paymentIntentData?.data;

  // Confirm payment mutation
  const confirmPaymentMutation = useMutation({
    mutationFn: (paymentIntentId: string) =>
      paymentsApi.confirmPayment(paymentIntentId, orderIds),
    onSuccess: () => {
      setShowSuccessDialog(true);
    },
    onError: (error: any) => {
      const message = error.response?.data?.error || 'Failed to confirm payment';
      setPaymentError(message);
      toast({
        title: 'Payment Confirmation Failed',
        description: message,
        variant: 'destructive',
      });
    },
  });

  // Handle successful Stripe payment
  const handlePaymentSuccess = (paymentIntentId: string) => {
    confirmPaymentMutation.mutate(paymentIntentId);
  };

  // Handle payment error
  const handlePaymentError = (error: string) => {
    setPaymentError(error);
  };

  // Handle success dialog close
  const handleSuccessClose = () => {
    setShowSuccessDialog(false);
    navigate('/orders');
  };

  // Loading state
  if (isLoadingIntent || !stripe) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Skeleton className="h-12 w-48 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  // Error loading payment intent
  if (intentError || !paymentIntent) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Button variant="ghost" onClick={() => navigate('/orders')} className="mb-6">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Orders
        </Button>

        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {(intentError as any)?.response?.data?.error ||
              'Failed to load payment information'}
          </AlertDescription>
        </Alert>

        <div className="mt-6 text-center">
          <p className="text-muted-foreground mb-4">
            Unable to process payment at this time
          </p>
          <Button onClick={() => navigate('/orders')}>
            View My Orders
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Header */}
      <Button
        variant="ghost"
        onClick={() => navigate('/orders')}
        className="mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Orders
      </Button>

      <div className="flex items-center gap-3 mb-8">
        <CreditCard className="h-8 w-8 text-primary" />
        <h1 className="text-3xl font-bold">Complete Payment</h1>
      </div>

      {/* Payment Error */}
      {paymentError && !confirmPaymentMutation.isPending && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{paymentError}</AlertDescription>
        </Alert>
      )}

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Payment Form */}
        <div>
          <StripeCheckoutForm
            stripe={stripe}
            clientSecret={paymentIntent.client_secret}
            onSuccess={handlePaymentSuccess}
            onError={handlePaymentError}
            amount={paymentIntent.amount}
          />
        </div>

        {/* Payment Summary */}
        <div>
          <PaymentSummary paymentIntent={paymentIntent} />
        </div>
      </div>

      {/* Success Dialog */}
      <AlertDialog open={showSuccessDialog} onOpenChange={setShowSuccessDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <div className="flex justify-center mb-4">
              <div className="p-3 bg-green-100 rounded-full">
                <CheckCircle className="h-12 w-12 text-green-600" />
              </div>
            </div>
            <AlertDialogTitle className="text-center text-2xl">
              Payment Successful!
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center space-y-4">
              <p className="text-base">
                Your payment has been processed successfully.
              </p>
              <p className="text-sm text-muted-foreground">
                You can view your order details in "My Orders"
              </p>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="flex flex-col gap-2">
            <Button onClick={handleSuccessClose} className="w-full">
              {confirmPaymentMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Confirming...
                </>
              ) : (
                'View My Orders'
              )}
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}