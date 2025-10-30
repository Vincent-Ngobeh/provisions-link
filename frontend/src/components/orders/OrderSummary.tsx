// frontend/src/components/orders/OrderSummary.tsx
// Order pricing breakdown

import { OrderDetail } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

interface OrderSummaryProps {
  order: OrderDetail;
}

export function OrderSummary({ order }: OrderSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Order Summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Subtotal</span>
          <span>£{parseFloat(order.subtotal).toFixed(2)}</span>
        </div>

        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">VAT</span>
          <span>£{parseFloat(order.vat_amount).toFixed(2)}</span>
        </div>

        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Delivery Fee</span>
          <span>
            {parseFloat(order.delivery_fee) === 0
              ? 'FREE'
              : `£${parseFloat(order.delivery_fee).toFixed(2)}`}
          </span>
        </div>

        <Separator />

        <div className="flex justify-between font-bold text-lg">
          <span>Total</span>
          <span>£{parseFloat(order.total).toFixed(2)}</span>
        </div>

        {order.marketplace_fee && (
          <>
            <Separator />
            <div className="pt-2 space-y-2 text-sm text-muted-foreground">
              <div className="flex justify-between">
                <span>Marketplace Fee</span>
                <span>£{parseFloat(order.marketplace_fee).toFixed(2)}</span>
              </div>
              {order.vendor_payout && (
                <div className="flex justify-between">
                  <span>Vendor Payout</span>
                  <span>£{parseFloat(order.vendor_payout).toFixed(2)}</span>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}