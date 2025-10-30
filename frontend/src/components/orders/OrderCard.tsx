// frontend/src/components/orders/OrderCard.tsx
import { Order } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { OrderStatusBadge } from './OrderStatusBadge';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Package, Calendar, Store, ArrowRight, Users } from 'lucide-react';

interface OrderCardProps {
  order: Order;
  onClick: () => void;
}

export function OrderCard({ order, onClick }: OrderCardProps) {
  // Check if this order came from group buying
  const isGroupBuyOrder = order.group !== undefined && order.group !== null;

  return (
    <Card className="hover:shadow-md transition-shadow cursor-pointer" onClick={onClick}>
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <h3 className="font-semibold text-lg">{order.reference_number}</h3>
              {/* ADDED: Group Buy Badge */}
              {isGroupBuyOrder && (
                <Badge className="bg-green-100 text-green-800 border-green-300 hover:bg-green-200">
                  <Users className="h-3 w-3 mr-1" />
                  Group Buy
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm text-muted-foreground flex-wrap">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                {new Date(order.created_at).toLocaleDateString('en-GB', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })}
              </div>
              <div className="flex items-center gap-2">
                <Package className="h-4 w-4" />
                {order.items_count} {order.items_count === 1 ? 'item' : 'items'}
              </div>
            </div>
          </div>
          <OrderStatusBadge status={order.status} />
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Store className="h-4 w-4" />
            <span>{order.vendor_name}</span>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Total</p>
              <p className="text-lg font-bold">£{parseFloat(order.total).toFixed(2)}</p>
            </div>
            <Button variant="ghost" size="icon">
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}