// frontend/src/components/orders/OrderTimeline.tsx
// Visual timeline showing order status progression

import { OrderDetail } from '@/types';
import { cn } from '@/lib/utils';
import {
  Clock,
  CreditCard,
  PackageSearch,
  Truck,
  CheckCircle,
  XCircle,
} from 'lucide-react';

interface OrderTimelineProps {
  order: OrderDetail;
}

interface TimelineStep {
  status: string;
  label: string;
  icon: React.ReactNode;
  date?: string;
}

export function OrderTimeline({ order }: OrderTimelineProps) {
  const steps: TimelineStep[] = [
    {
      status: 'pending',
      label: 'Order Placed',
      icon: <Clock className="h-5 w-5" />,
      date: order.created_at,
    },
    {
      status: 'paid',
      label: 'Payment Confirmed',
      icon: <CreditCard className="h-5 w-5" />,
      date: order.paid_at,
    },
    {
      status: 'processing',
      label: 'Processing',
      icon: <PackageSearch className="h-5 w-5" />,
    },
    {
      status: 'shipped',
      label: 'Shipped',
      icon: <Truck className="h-5 w-5" />,
    },
    {
      status: 'delivered',
      label: 'Delivered',
      icon: <CheckCircle className="h-5 w-5" />,
      date: order.delivered_at,
    },
  ];

  // Handle cancelled/refunded orders
  if (order.status === 'cancelled' || order.status === 'refunded') {
    return (
      <div className="flex items-center gap-3 p-4 bg-red-50 rounded-lg border border-red-200">
        <XCircle className="h-6 w-6 text-red-600" />
        <div>
          <p className="font-medium text-red-900">
            Order {order.status === 'cancelled' ? 'Cancelled' : 'Refunded'}
          </p>
          <p className="text-sm text-red-700">
            This order has been {order.status}.
          </p>
        </div>
      </div>
    );
  }

  const currentStepIndex = steps.findIndex((step) => step.status === order.status);

  return (
    <div className="space-y-8">
      {steps.map((step, index) => {
        const isCompleted = index <= currentStepIndex;
        const isCurrent = index === currentStepIndex;

        return (
          <div key={step.status} className="flex gap-4">
            {/* Icon */}
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors',
                  isCompleted
                    ? 'bg-primary border-primary text-primary-foreground'
                    : 'bg-background border-muted-foreground/30 text-muted-foreground'
                )}
              >
                {step.icon}
              </div>
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'w-0.5 h-16 mt-2 transition-colors',
                    isCompleted ? 'bg-primary' : 'bg-muted-foreground/20'
                  )}
                />
              )}
            </div>

            {/* Content */}
            <div className="flex-1 pb-8">
              <p
                className={cn(
                  'font-medium mb-1',
                  isCompleted ? 'text-foreground' : 'text-muted-foreground'
                )}
              >
                {step.label}
              </p>
              {step.date && (
                <p className="text-sm text-muted-foreground">
                  {new Date(step.date).toLocaleString('en-GB', {
                    day: 'numeric',
                    month: 'long',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              )}
              {isCurrent && !step.date && (
                <p className="text-sm text-primary font-medium">In Progress</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}