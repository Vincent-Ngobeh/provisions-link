// frontend/src/pages/VendorDashboardPage.tsx
// Private dashboard for vendor's own account

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { vendorsApi, ordersApi, productsApi } from '@/api/endpoints';
import { VendorStats } from '@/components/vendors/VendorStats';
import { OrderCard } from '@/components/orders/OrderCard';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import {
  LayoutDashboard,
  Package,
  TrendingUp,
  AlertCircle,
  ExternalLink,
  Info,
} from 'lucide-react';

export default function VendorDashboardPage() {
  const navigate = useNavigate();
  const { user, isVendor } = useAuth();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Redirect if not a vendor
  if (!isVendor) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-2xl font-bold mb-2">Vendor Access Required</h2>
        <p className="text-muted-foreground mb-4">
          You need a vendor account to access the dashboard.
        </p>
        <Button onClick={() => navigate('/')}>Go to Home</Button>
      </div>
    );
  }

  // Fetch vendor dashboard data
  const { data: dashboardData, isLoading: isLoadingDashboard } = useQuery({
    queryKey: ['vendor-dashboard'],
    queryFn: () => vendorsApi.dashboard(user!.id),
    enabled: isVendor,
  });

  // Fetch pending orders (filtered by vendor)
  const { data: ordersData, isLoading: isLoadingOrders } = useQuery({
    queryKey: ['vendor-pending-orders'],
    queryFn: () => ordersApi.list({ status: 'paid', vendor: user!.id }),
    enabled: isVendor,
  });

  // Fetch low stock products
  const { data: lowStockData, isLoading: isLoadingStock } = useQuery({
    queryKey: ['vendor-low-stock'],
    queryFn: () => productsApi.lowStock({ vendor: user!.id }),
    enabled: isVendor,
  });

  // Stripe onboarding mutation
  const onboardingMutation = useMutation({
    mutationFn: () => vendorsApi.generateOnboardingLink(user!.id),
    onSuccess: (response) => {
      const onboardingUrl = response.data.url;
      
      // Open Stripe onboarding in new window
      const stripeWindow = window.open(onboardingUrl, '_blank', 'width=800,height=800');
      
      if (!stripeWindow) {
        toast({
          title: 'Popup Blocked',
          description: 'Please allow popups for this site and try again.',
          variant: 'destructive',
        });
        return;
      }

      toast({
        title: 'Onboarding Started',
        description: 'Complete the Stripe setup in the new window.',
      });

      // Poll for completion (optional - you can also use webhooks)
      const pollInterval = setInterval(() => {
        if (stripeWindow.closed) {
          clearInterval(pollInterval);
          // Refresh dashboard to check if onboarding completed
          queryClient.invalidateQueries({ queryKey: ['vendor-dashboard'] });
        }
      }, 1000);
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.error || 'Failed to start onboarding. Please try again.',
        variant: 'destructive',
      });
    },
  });

  const handleCompleteOnboarding = () => {
    onboardingMutation.mutate();
  };

  const dashboard = dashboardData?.data;
  const pendingOrders = ordersData?.data?.results || [];
  const lowStockProducts = lowStockData?.data?.products || [];

  if (isLoadingDashboard) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <Skeleton className="h-12 w-64 mb-8" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <LayoutDashboard className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">Vendor Dashboard</h1>
        </div>
        <p className="text-muted-foreground">
          Welcome back, {dashboard?.business_name || 'Vendor'}
        </p>
      </div>

      {/* Stripe Onboarding Alert */}
      {!dashboard?.stripe_onboarding_complete && (
        <Alert className="mb-6 border-yellow-500 bg-yellow-50">
          <AlertCircle className="h-4 w-4 text-yellow-600" />
          <AlertDescription>
            <strong className="text-yellow-900">Complete your Stripe setup</strong>
            <p className="text-yellow-800 mt-1">
              You need to complete Stripe Connect onboarding to receive payments.
            </p>
            <Button 
              variant="outline" 
              size="sm" 
              className="mt-2"
              onClick={handleCompleteOnboarding}
              disabled={onboardingMutation.isPending}
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              {onboardingMutation.isPending ? 'Loading...' : 'Complete Onboarding'}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Statistics */}
      {dashboard && <VendorStats dashboard={dashboard} />}

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
        {/* Pending Orders */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <Package className="h-5 w-5" />
                Pending Orders ({pendingOrders.length})
              </CardTitle>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => navigate('/orders?vendor=true')}
              >
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {isLoadingOrders ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-24" />
                ))}
              </div>
            ) : pendingOrders.length === 0 ? (
              <div className="text-center py-8">
                <Package className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
                <p className="text-muted-foreground">No pending orders</p>
              </div>
            ) : (
              <div className="space-y-4">
                {pendingOrders.slice(0, 3).map((order) => (
                  <OrderCard
                    key={order.id}
                    order={order}
                    onClick={() => navigate(`/orders/${order.id}`)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Low Stock Products */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Low Stock Alert ({lowStockProducts.length})
              </CardTitle>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => navigate(`/products?vendor=${user!.id}`)}
              >
                View All
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {isLoadingStock ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-20" />
                ))}
              </div>
            ) : lowStockProducts.length === 0 ? (
              <div className="text-center py-8">
                <TrendingUp className="h-12 w-12 mx-auto text-muted-foreground mb-2" />
                <p className="text-muted-foreground">All products well stocked</p>
              </div>
            ) : (
              <div className="space-y-3">
                {lowStockProducts.slice(0, 5).map((product: any) => (
                  <div
                    key={product.id}
                    className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 cursor-pointer"
                    onClick={() => navigate(`/products/${product.id}`)}
                  >
                    <div className="flex items-center gap-3">
                      {product.primary_image && (
                        <img
                          src={product.primary_image}
                          alt={product.name}
                          className="w-10 h-10 object-cover rounded"
                        />
                      )}
                      <div>
                        <p className="font-medium text-sm">{product.name}</p>
                        <p className="text-xs text-muted-foreground">
                          Stock: {product.stock_quantity} {product.unit}
                        </p>
                      </div>
                    </div>
                    <Button variant="outline" size="sm">
                      Update
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* FSA Info */}
      {dashboard?.fsa_rating_value && (
        <Alert className="mt-6">
          <Info className="h-4 w-4" />
          <AlertDescription>
            <strong>FSA Rating: {dashboard.fsa_rating_value}/5</strong>
            {dashboard.fsa_last_checked && (
              <p className="text-sm mt-1">
                Last checked:{' '}
                {new Date(dashboard.fsa_last_checked).toLocaleDateString('en-GB')}
              </p>
            )}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}