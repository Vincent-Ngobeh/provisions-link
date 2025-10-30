// frontend/src/components/cart/CartSummary.tsx
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';
import type { Cart, CartSummaryResponse } from '@/types';

interface CartSummaryProps {
  cart: Cart;
  vendorSummary?: CartSummaryResponse;
}

export function CartSummary({ cart, vendorSummary }: CartSummaryProps) {
  const subtotal = parseFloat(cart.subtotal || '0');
  const vatTotal = parseFloat(cart.vat_total || '0');
  const grandTotal = parseFloat(cart.grand_total || '0');

  return (
    <Card>
      <CardHeader>
        <CardTitle>Order Summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Vendor minimum order warnings */}
        {vendorSummary?.vendors && vendorSummary.vendors.some(v => !v.meets_minimum) && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              <div className="space-y-2">
                <p className="font-medium">Minimum order requirements not met:</p>
                {vendorSummary.vendors.filter(v => !v.meets_minimum).map(vendor => (
                  <div key={vendor.vendor_id} className="text-xs">
                    <span className="font-medium">{vendor.vendor_name}:</span> Need £{(
                      parseFloat(vendor.min_order_value) - parseFloat(vendor.subtotal)
                    ).toFixed(2)} more (min: £{vendor.min_order_value})
                  </div>
                ))}
              </div>
            </AlertDescription>
          </Alert>
        )}

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Subtotal</span>
            <span>£{subtotal.toFixed(2)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">VAT</span>
            <span>£{vatTotal.toFixed(2)}</span>
          </div>
          <Separator />
          <div className="flex justify-between font-bold text-lg">
            <span>Total</span>
            <span>£{grandTotal.toFixed(2)}</span>
          </div>
        </div>

        {vendorSummary?.vendors && vendorSummary.vendors.length > 1 && (
          <>
            <Separator />
            <p className="text-xs text-muted-foreground text-center">
              Items from {vendorSummary.vendors.length} different vendors
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}