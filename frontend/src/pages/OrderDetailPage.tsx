// frontend/src/pages/OrderDetailPage.tsx
// Detailed order view with status tracking and actions

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { OrderTimeline } from '@/components/orders/OrderTimeline';
import { OrderItemsTable } from '@/components/orders/OrderItemsTable';
import { OrderSummary } from '@/components/orders/OrderSummary';
import { OrderStatusBadge } from '@/components/orders/OrderStatusBadge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  ArrowLeft,
  Package,
  MapPin,
  Store,
  Calendar,
  AlertCircle,
  XCircle,
  AlertTriangle,
} from 'lucide-react';

export default function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, isVendor } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [newStatus, setNewStatus] = useState<string>('');
  const [showCancelDialog, setShowCancelDialog] = useState(false);

  // Fetch order details
  const { data: orderData, isLoading } = useQuery({
    queryKey: ['order', id],
    queryFn: () => ordersApi.get(parseInt(id!)),
    enabled: !!id,
  });

  const order = orderData?.data;

  // Update status mutation
  const updateStatusMutation = useMutation({
    mutationFn: ({ status }: { status: string }) =>
      ordersApi.updateStatus(parseInt(id!), status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order', id] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast({
        title: 'Status Updated',
        description: 'Order status has been updated successfully.',
      });
      setNewStatus('');
    },
    onError: (error: any) => {
      toast({
        title: 'Update Failed',
        description: error.response?.data?.error || 'Failed to update order status.',
        variant: 'destructive',
      });
    },
  });

  // Cancel order mutation
  const cancelOrderMutation = useMutation({
    mutationFn: () => ordersApi.cancel(parseInt(id!)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['order', id] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast({
        title: 'Order Cancelled',
        description: 'Your order has been cancelled successfully.',
      });
      setShowCancelDialog(false);
    },
    onError: (error: any) => {
      toast({
        title: 'Cancellation Failed',
        description: error.response?.data?.error || 'Failed to cancel order.',
        variant: 'destructive',
      });
    },
  });

  const handleStatusUpdate = () => {
    if (!newStatus) return;
    updateStatusMutation.mutate({ status: newStatus });
  };

  const handleCancelOrder = () => {
    cancelOrderMutation.mutate();
  };

  // Permission checks
  // Fixed: Simplified permission check - backend ensures vendors only see their own orders
  const canUpdateStatus = order && (user?.is_staff || isVendor);

  const canCancel =
    order &&
    !isVendor &&
    order.buyer.id === user?.id &&
    ['pending', 'paid'].includes(order.status);

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-5xl">
        <Skeleton className="h-12 w-32 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-96" />
            <Skeleton className="h-64" />
          </div>
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-2xl font-bold mb-2">Order Not Found</h2>
        <p className="text-muted-foreground mb-4">
          This order doesn't exist or you don't have permission to view it.
        </p>
        <Button onClick={() => navigate('/orders')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Orders
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-5xl">
      {/* Back Button */}
      <Button variant="ghost" onClick={() => navigate('/orders')} className="mb-6">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Orders
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Order Header */}
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-2xl mb-2">
                    Order {order.reference_number}
                  </CardTitle>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      {new Date(order.created_at).toLocaleDateString('en-GB', {
                        day: 'numeric',
                        month: 'long',
                        year: 'numeric',
                      })}
                    </div>
                    <div className="flex items-center gap-2">
                      <Package className="h-4 w-4" />
                      {order.items.length} {order.items.length === 1 ? 'item' : 'items'}
                    </div>
                  </div>
                </div>
                <OrderStatusBadge status={order.status} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Vendor Info */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Store className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Vendor</span>
                  </div>
                  <p className="text-sm">{order.vendor.business_name}</p>
                  
                  {/* Warning for unverified vendors */}
                  {(!order.vendor.is_approved || !order.vendor.stripe_onboarding_complete) && (
                    <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800 flex items-start gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                      <span>
                        This order was placed before vendor verification requirements. You can still cancel it.
                      </span>
                    </div>
                  )}
                  
                  {order.vendor.phone_number && (
                    <p className="text-sm text-muted-foreground mt-1">{order.vendor.phone_number}</p>
                  )}
                </div>

                {/* Delivery Address */}
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Delivery Address</span>
                  </div>
                  <p className="text-sm">
                    {order.delivery_address.line1}
                    {order.delivery_address.line2 && `, ${order.delivery_address.line2}`}
                  </p>
                  <p className="text-sm">
                    {order.delivery_address.city}, {order.delivery_address.postcode}
                  </p>
                </div>
              </div>

              {order.delivery_notes && (
                <div className="mt-4 pt-4 border-t">
                  <p className="text-sm font-medium mb-1">Delivery Notes</p>
                  <p className="text-sm text-muted-foreground">{order.delivery_notes}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Order Timeline */}
          <Card>
            <CardHeader>
              <CardTitle>Order Status</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderTimeline order={order} />
            </CardContent>
          </Card>

          {/* Order Items */}
          <Card>
            <CardHeader>
              <CardTitle>Order Items</CardTitle>
            </CardHeader>
            <CardContent>
              <OrderItemsTable items={order.items} />
            </CardContent>
          </Card>

          {/* Vendor Actions */}
          {canUpdateStatus && (
            <Card>
              <CardHeader>
                <CardTitle>Update Order Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex gap-4">
                  <Select value={newStatus} onValueChange={setNewStatus}>
                    <SelectTrigger className="flex-1">
                      <SelectValue placeholder="Select new status" />
                    </SelectTrigger>
                    <SelectContent>
                      {order.status === 'pending' && (
                        <>
                          <SelectItem value="paid">Mark as Paid</SelectItem>
                          <SelectItem value="cancelled">Cancel Order</SelectItem>
                        </>
                      )}
                      {order.status === 'paid' && (
                        <>
                          <SelectItem value="processing">Start Processing</SelectItem>
                          <SelectItem value="cancelled">Cancel Order</SelectItem>
                        </>
                      )}
                      {order.status === 'processing' && (
                        <>
                          <SelectItem value="shipped">Mark as Shipped</SelectItem>
                          <SelectItem value="cancelled">Cancel Order</SelectItem>
                        </>
                      )}
                      {order.status === 'shipped' && (
                        <SelectItem value="delivered">Mark as Delivered</SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                  <Button
                    onClick={handleStatusUpdate}
                    disabled={!newStatus || updateStatusMutation.isPending}
                  >
                    {updateStatusMutation.isPending ? 'Updating...' : 'Update Status'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Order Summary */}
          <OrderSummary order={order} />

          {/* Actions */}
          {canCancel && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Order Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <Button
                  variant="destructive"
                  className="w-full"
                  onClick={() => setShowCancelDialog(true)}
                  disabled={cancelOrderMutation.isPending}
                >
                  <XCircle className="h-4 w-4 mr-2" />
                  Cancel Order
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Payment Info */}
          {order.stripe_payment_intent_id && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Payment Information</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Payment ID</span>
                    <span className="font-mono text-xs">
                      {order.stripe_payment_intent_id.slice(0, 20)}...
                    </span>
                  </div>
                  {order.paid_at && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Paid At</span>
                      <span>
                        {new Date(order.paid_at).toLocaleDateString('en-GB', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* Cancel Confirmation Dialog */}
      <AlertDialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel Order?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to cancel this order? This action cannot be undone.
              {order.status === 'paid' &&
                ' Your payment will be refunded to your original payment method.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep Order</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleCancelOrder}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Cancel Order
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}