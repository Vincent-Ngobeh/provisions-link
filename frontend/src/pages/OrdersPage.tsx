// frontend/src/pages/OrdersPage.tsx
// Orders list page with filtering and status management

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ordersApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { OrderCard } from '@/components/orders/OrderCard';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Package,
  Filter,
  AlertCircle,
  TrendingUp,
  Clock,
  CheckCircle,
} from 'lucide-react';

export default function OrdersPage() {
  const navigate = useNavigate();
  const { user, isVendor } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Fetch orders with filters
  const { data: ordersData, isLoading } = useQuery({
    queryKey: ['orders', statusFilter],
    queryFn: () =>
      ordersApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
      }),
    enabled: !!user,
  });

  const orders = ordersData?.data?.results || [];

  // Calculate statistics
  const stats = {
    total: orders.length,
    pending: orders.filter((o) => o.status === 'pending').length,
    processing: orders.filter((o) => o.status === 'processing').length,
    delivered: orders.filter((o) => o.status === 'delivered').length,
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Package className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">
            {isVendor ? 'Order Management' : 'My Orders'}
          </h1>
        </div>
        <p className="text-muted-foreground">
          {isVendor
            ? 'Manage incoming orders and track fulfillment'
            : 'View your order history and track deliveries'}
        </p>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-full">
              <Package className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.total}</p>
              <p className="text-sm text-muted-foreground">Total Orders</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 rounded-full">
              <Clock className="h-5 w-5 text-yellow-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.pending}</p>
              <p className="text-sm text-muted-foreground">Pending</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-full">
              <TrendingUp className="h-5 w-5 text-orange-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.processing}</p>
              <p className="text-sm text-muted-foreground">Processing</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-full">
              <CheckCircle className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.delivered}</p>
              <p className="text-sm text-muted-foreground">Delivered</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card rounded-lg border p-4 mb-6">
        <div className="flex items-center gap-2 mb-4 text-sm font-medium">
          <Filter className="h-4 w-4" />
          Filters
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Status</label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Orders</SelectItem>
                <SelectItem value="pending">Pending Payment</SelectItem>
                <SelectItem value="paid">Paid</SelectItem>
                <SelectItem value="processing">Processing</SelectItem>
                <SelectItem value="shipped">Shipped</SelectItem>
                <SelectItem value="delivered">Delivered</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
                <SelectItem value="refunded">Refunded</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Orders List */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : orders.length === 0 ? (
        <div className="text-center py-12">
          <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No orders found</h3>
          <p className="text-muted-foreground mb-4">
            {statusFilter === 'all'
              ? "You haven't placed any orders yet"
              : `No orders with status: ${statusFilter}`}
          </p>
          {statusFilter !== 'all' && (
            <Button variant="outline" onClick={() => setStatusFilter('all')}>
              View All Orders
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              onClick={() => navigate(`/orders/${order.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}