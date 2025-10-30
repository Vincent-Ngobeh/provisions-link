// frontend/src/components/orders/OrderStatusBadge.tsx
// Status badge with appropriate colors

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface OrderStatusBadgeProps {
  status: string;
  className?: string;
}

const STATUS_CONFIG: Record<string, {
  label: string;
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  className: string;
}> = {
  pending: {
    label: 'Pending Payment',
    variant: 'outline',
    className: 'border-yellow-500 text-yellow-700 bg-yellow-50',
  },
  paid: {
    label: 'Paid',
    variant: 'default',
    className: 'bg-blue-500 text-white',
  },
  processing: {
    label: 'Processing',
    variant: 'default',
    className: 'bg-orange-500 text-white',
  },
  shipped: {
    label: 'Shipped',
    variant: 'default',
    className: 'bg-purple-500 text-white',
  },
  delivered: {
    label: 'Delivered',
    variant: 'default',
    className: 'bg-green-500 text-white',
  },
  cancelled: {
    label: 'Cancelled',
    variant: 'destructive',
    className: 'bg-red-500 text-white',
  },
  refunded: {
    label: 'Refunded',
    variant: 'secondary',
    className: 'bg-gray-500 text-white',
  },
};

export function OrderStatusBadge({ status, className }: OrderStatusBadgeProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.pending;

  return (
    <Badge className={cn(config.className, className)}>
      {config.label}
    </Badge>
  );
}