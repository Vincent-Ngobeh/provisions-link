import apiClient from '@/lib/axios';
import type { ApiResponse } from '@/types';

export interface PaymentIntent {
  payment_intent_id: string;
  client_secret: string;
  amount: number; // in pence
  currency: string;
  vendor: {
    id: number;
    name: string;
    stripe_account_id: string;
  };
  orders: Array<{
    id: number;
    reference: string;
    total: string;
  }>;
  commission: number;
  vendor_payout: number;
}

export interface PaymentConfirmation {
  success: boolean;
  orders_updated: number;
  orders_already_paid: number;
  payment_intent_id: string;
  orders: any[];
}

export interface PaymentStatus {
  payment_intent_id: string;
  status: string;
  amount: number;
  currency: string;
  created: string;
  metadata?: Record<string, any>;
  payment_method?: string;
  next_action?: any;
}

export const paymentsApi = {
  /**
   * Create a payment intent for orders
   */
  createIntent: async (orderIds: number[]): Promise<ApiResponse<PaymentIntent>> => {
    const { data } = await apiClient.post<PaymentIntent>(
      '/payments/create-intent/',
      { order_ids: orderIds }
    );
    return { data };
  },

  /**
   * Confirm payment after Stripe confirms it client-side
   */
  confirmPayment: async (
    paymentIntentId: string,
    orderIds: number[]
  ): Promise<ApiResponse<PaymentConfirmation>> => {
    const { data } = await apiClient.post<PaymentConfirmation>(
      '/payments/confirm-payment/',
      {
        payment_intent_id: paymentIntentId,
        order_ids: orderIds,
      }
    );
    return { data };
  },

  /**
   * Get payment status
   */
  getStatus: async (intentId: string): Promise<ApiResponse<PaymentStatus>> => {
    const { data } = await apiClient.get<PaymentStatus>(
      `/payments/payment-status/${intentId}/`
    );
    return { data };
  },
};