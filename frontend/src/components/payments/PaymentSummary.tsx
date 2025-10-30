import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Package, Store, CreditCard } from 'lucide-react';
import type { PaymentIntent } from '@/api/paymentsApi';
import { formatAmount } from '@/lib/stripe';

interface PaymentSummaryProps {
  paymentIntent: PaymentIntent;
}

export function PaymentSummary({ paymentIntent }: PaymentSummaryProps) {
  const { vendor, orders, amount, commission, vendor_payout } = paymentIntent;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CreditCard className="h-5 w-5" />
          Payment Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Vendor Info */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Store className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-medium">Vendor</p>
          </div>
          <p className="text-base font-semibold">{vendor.name}</p>
        </div>

        <Separator />

        {/* Orders */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Package className="h-4 w-4 text-muted-foreground" />
            <p className="text-sm font-medium">
              Orders ({orders.length})
            </p>
          </div>
          <div className="space-y-2">
            {orders.map((order) => (
              <div
                key={order.id}
                className="flex justify-between text-sm"
              >
                <span className="text-muted-foreground">
                  Order #{order.reference}
                </span>
                <span className="font-medium">
                  £{parseFloat(order.total).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Amount Breakdown */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Subtotal</span>
            <span>{formatAmount(amount)}</span>
          </div>
          
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Platform Fee</span>
            <span className="text-muted-foreground">
              -{formatAmount(commission)}
            </span>
          </div>
          
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Vendor Receives</span>
            <span className="text-green-600">
              {formatAmount(vendor_payout)}
            </span>
          </div>

          <Separator />

          <div className="flex justify-between font-bold text-lg pt-2">
            <span>Total</span>
            <span className="text-primary">{formatAmount(amount)}</span>
          </div>
        </div>

        {/* Test Mode Notice */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
          <p className="text-xs text-yellow-800 font-medium mb-1">
             Test Mode
          </p>
          <p className="text-xs text-yellow-700">
            Use test card: <code className="font-mono bg-yellow-100 px-1 rounded">4242 4242 4242 4242</code>
          </p>
          <p className="text-xs text-yellow-700 mt-1">
            Any CVC, future expiry date
          </p>
        </div>
      </CardContent>
    </Card>
  );
}