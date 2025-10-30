import { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

const stripePromise = loadStripe(process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY!);

export function StripeTestPayment({ orderId }: { orderId: number }) {
  const [processing, setProcessing] = useState(false);
  const [cardNumber, setCardNumber] = useState('4242424242424242');

  const handleTestPayment = async () => {
    setProcessing(true);
    
    try {
      // Get payment intent from your API
      const response = await fetch(`/api/integrations/stripe/create_payment_intent/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId }),
      });
      
      const data = await response.json();
      const stripe = await stripePromise;
      
      if (!stripe) {
        throw new Error('Stripe not loaded');
      }
      
      // In production, you'd use Stripe Elements here
      console.log('Payment intent created:', data);
      console.log('Use this client_secret in Stripe.js:', data.client_secret);
      
      alert('Check console for payment details. In production, this would process the card.');
    } catch (error) {
      console.error('Payment error:', error);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test Stripe Payment</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label>Test Card Number</label>
          <Input
            value={cardNumber}
            onChange={(e) => setCardNumber(e.target.value)}
            placeholder="4242 4242 4242 4242"
          />
          <p className="text-sm text-muted-foreground mt-1">
            Use Stripe test cards only
          </p>
        </div>
        
        <Button 
          onClick={handleTestPayment}
          disabled={processing}
          className="w-full"
        >
          {processing ? 'Processing...' : 'Test Payment'}
        </Button>
        
        <div className="text-xs text-muted-foreground">
          <p>Test cards:</p>
          <ul className="ml-4">
            <li>Success: 4242 4242 4242 4242</li>
            <li>Decline: 4000 0000 0000 0002</li>
            <li>3D Secure: 4000 0025 0000 3155</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}