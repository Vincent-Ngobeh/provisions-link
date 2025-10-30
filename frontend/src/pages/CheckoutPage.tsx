import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { cartApi, addressesApi } from '@/api/endpoints';
import { useCart } from '@/contexts/CartContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import {
  ArrowLeft,
  Package,
  MapPin,
  Store,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import type { VendorCartSummary } from '@/types';

export default function CheckoutPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { refreshCart } = useCart();

  const [deliveryNotes, setDeliveryNotes] = useState('');

  // Fetch cart summary
  const { data: summaryData, isLoading: isLoadingSummary } = useQuery({
    queryKey: ['cart-summary'],
    queryFn: () => cartApi.getSummary(),
  });

  // Fetch default address
  const { data: addressData, isLoading: isLoadingAddress } = useQuery({
    queryKey: ['default-address'],
    queryFn: () => addressesApi.getDefault(),
  });

  const summary = summaryData?.data;
  const defaultAddress = addressData?.data;
  const isLoading = isLoadingSummary || isLoadingAddress;

  // Checkout mutation
  const checkoutMutation = useMutation({
    mutationFn: (data: { delivery_address_id: number; delivery_notes?: string }) =>
      cartApi.checkout(data),
    onSuccess: (response) => {
      // Extract order IDs from response
      const orderIds = response.data.orders.map((o: any) => o.order_id).join(',');
      
      // Refresh cart
      refreshCart();
      
      // Navigate to payment page with order IDs
      navigate(`/payment?orderIds=${orderIds}`);
    },
    onError: (error: any) => {
      toast({
        title: 'Checkout Failed',
        description: error.response?.data?.error || 'Failed to complete checkout',
        variant: 'destructive',
      });
    },
  });

  const handleCheckout = () => {
    if (!defaultAddress) {
      toast({
        title: 'No Address',
        description: 'Please add a delivery address first',
        variant: 'destructive',
      });
      navigate('/profile');
      return;
    }

    checkoutMutation.mutate({
      delivery_address_id: defaultAddress.id,
      delivery_notes: deliveryNotes || undefined,
    });
  };

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Skeleton className="h-12 w-48 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-64" />
            <Skeleton className="h-48" />
          </div>
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!summary || summary.vendors.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-2xl font-bold mb-2">Your cart is empty</h2>
        <p className="text-muted-foreground mb-4">Add some items to checkout</p>
        <Button onClick={() => navigate('/products')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Browse Products
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Header */}
      <Button variant="ghost" onClick={() => navigate('/cart')} className="mb-6">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Cart
      </Button>

      <div className="flex items-center gap-3 mb-8">
        <Package className="h-8 w-8 text-primary" />
        <h1 className="text-3xl font-bold">Checkout</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Delivery Address */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MapPin className="h-5 w-5" />
                Delivery Address
              </CardTitle>
            </CardHeader>
            <CardContent>
              {defaultAddress ? (
                <div>
                  <p className="font-medium">{defaultAddress.recipient_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {defaultAddress.line1}
                    {defaultAddress.line2 && `, ${defaultAddress.line2}`}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {defaultAddress.city}, {defaultAddress.postcode}
                  </p>
                  <Button
                    variant="link"
                    className="mt-2 px-0"
                    onClick={() => navigate('/profile')}
                  >
                    Change Address
                  </Button>
                </div>
              ) : (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    No delivery address found.{' '}
                    <Button
                      variant="link"
                      className="px-0 h-auto"
                      onClick={() => navigate('/profile')}
                    >
                      Add one in your profile
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          {/* Delivery Notes */}
          <Card>
            <CardHeader>
              <CardTitle>Delivery Notes (Optional)</CardTitle>
            </CardHeader>
            <CardContent>
              <Label htmlFor="delivery-notes" className="text-sm text-muted-foreground mb-2 block">
                Any special instructions for delivery
              </Label>
              <Textarea
                id="delivery-notes"
                placeholder="e.g., Leave at reception, Call on arrival..."
                value={deliveryNotes}
                onChange={(e) => setDeliveryNotes(e.target.value)}
                rows={3}
              />
            </CardContent>
          </Card>

          {/* Orders by Vendor */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Store className="h-5 w-5" />
                Orders to be Created
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertDescription>
                  Your cart contains items from {summary.total_vendors} vendor
                  {summary.total_vendors > 1 ? 's' : ''}. We'll create separate orders for each vendor.
                </AlertDescription>
              </Alert>

              {summary.vendors.map((vendor: VendorCartSummary, index: number) => (
                <div key={vendor.vendor_id}>
                  {index > 0 && <Separator className="my-4" />}
                  
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold">{vendor.vendor_name}</h3>
                        <p className="text-sm text-muted-foreground">
                          {vendor.items_count} {vendor.items_count === 1 ? 'item' : 'items'}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-muted-foreground">Order Total</p>
                        <p className="text-lg font-bold">£{parseFloat(vendor.total).toFixed(2)}</p>
                      </div>
                    </div>

                    {/* Minimum order check */}
                    {!vendor.meets_minimum && (
                      <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription className="text-xs">
                          Minimum order value: £{vendor.min_order_value}. 
                          Add £{(parseFloat(vendor.min_order_value) - parseFloat(vendor.subtotal)).toFixed(2)} more.
                        </AlertDescription>
                      </Alert>
                    )}

                    {/* Items list */}
                    <div className="space-y-2">
                      {vendor.items.map((item) => (
                        <div key={item.id} className="flex justify-between text-sm">
                          <span className="text-muted-foreground">
                            {item.quantity}x {item.product.name}
                          </span>
                          <span>£{parseFloat(item.total_with_vat).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar - Order Summary */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Order Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Subtotal</span>
                <span>£{parseFloat(summary.grand_total).toFixed(2)}</span>
              </div>

              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Delivery</span>
                <span className="text-green-600">Calculated per vendor</span>
              </div>

              <Separator />

              <div className="flex justify-between font-bold text-lg">
                <span>Total</span>
                <span>£{parseFloat(summary.grand_total).toFixed(2)}</span>
              </div>

              <Separator />

              <Button
                className="w-full"
                size="lg"
                onClick={handleCheckout}
                disabled={
                  checkoutMutation.isPending ||
                  !defaultAddress ||
                  summary.vendors.some((v: VendorCartSummary) => !v.meets_minimum)
                }
              >
                {checkoutMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Package className="h-4 w-4 mr-2" />
                    Place {summary.total_vendors} Order{summary.total_vendors > 1 ? 's' : ''}
                  </>
                )}
              </Button>

              <p className="text-xs text-center text-muted-foreground">
                You'll be redirected to payment after placing your orders
              </p>
            </CardContent>
          </Card>

          {/* Info Card */}
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              <strong>Multiple Orders:</strong> Each vendor will receive a separate order.
              You'll be able to track each order individually in "My Orders".
            </AlertDescription>
          </Alert>
        </div>
      </div>
    </div>
  );
}