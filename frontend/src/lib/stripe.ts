import { loadStripe, Stripe } from '@stripe/stripe-js';

let stripePromise: Promise<Stripe | null>;

/**
 * Get Stripe instance (singleton pattern)
 */
export const getStripe = (): Promise<Stripe | null> => {
  if (!stripePromise) {
    const publishableKey = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;
    
    if (!publishableKey) {
      console.error('Stripe publishable key not configured');
      return Promise.resolve(null);
    }
    
    stripePromise = loadStripe(publishableKey);
  }
  
  return stripePromise;
};

/**
 * Format amount in pence to pounds
 */
export const formatAmount = (amountInPence: number): string => {
  return `£${(amountInPence / 100).toFixed(2)}`;
};

/**
 * Stripe test card numbers for development
 */
export const TEST_CARDS = {
  success: '4242 4242 4242 4242',
  decline: '4000 0000 0000 0002',
  requiresAuthentication: '4000 0025 0000 3155',
  insufficientFunds: '4000 0000 0000 9995',
};