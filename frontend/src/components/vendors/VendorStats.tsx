// frontend/src/components/vendors/VendorStats.tsx
// Dashboard statistics cards

import { VendorDashboard } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import {
  TrendingUp,
  Clock,
  AlertTriangle,
  DollarSign,
} from 'lucide-react';

interface VendorStatsProps {
  dashboard: VendorDashboard;
}

export function VendorStats({ dashboard }: VendorStatsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      {/* Today's Revenue */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-full">
              <DollarSign className="h-6 w-6 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Today's Revenue</p>
              <p className="text-2xl font-bold">
                £{parseFloat(dashboard.today_revenue).toFixed(2)}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pending Orders */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-100 rounded-full">
              <Clock className="h-6 w-6 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Pending Orders</p>
              <p className="text-2xl font-bold">{dashboard.pending_orders}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Low Stock */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-100 rounded-full">
              <AlertTriangle className="h-6 w-6 text-red-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Low Stock Items</p>
              <p className="text-2xl font-bold">{dashboard.low_stock_products}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Commission Rate */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-full">
              <TrendingUp className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Commission Rate</p>
              <p className="text-2xl font-bold">
                {parseFloat(dashboard.commission_rate) * 100}%
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}