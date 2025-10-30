// frontend/src/components/buying-groups/GroupCard.tsx
// Card component for displaying buying group in list view

import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { MapPin, Tag, Store, ArrowRight } from 'lucide-react';
import { GroupProgress } from './GroupProgress';
import { CountdownTimer } from './CountdownTimer';
import type { BuyingGroup } from '@/types';

interface GroupCardProps {
  group: BuyingGroup;
  showLocation?: boolean;
  showVendor?: boolean;
}

export function GroupCard({ 
  group, 
  showLocation = true,
  showVendor = true 
}: GroupCardProps) {
  const navigate = useNavigate();

  const statusConfig = {
    open: { label: 'Active', className: 'bg-green-100 text-green-800' },
    active: { label: 'Target Reached', className: 'bg-blue-100 text-blue-800' },
    failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
    completed: { label: 'Completed', className: 'bg-gray-100 text-gray-800' },
  };

  const status = statusConfig[group.status] || statusConfig.open;
  const discountValue = parseFloat(group.discount_percent);

  return (
    <Card className="hover:shadow-md transition-shadow cursor-pointer group">
      <CardHeader className="pb-3" onClick={() => navigate(`/buying-groups/${group.id}`)}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <h3 className="font-semibold text-lg group-hover:text-primary transition-colors">
              {group.product_name}
            </h3>
            
            <div className="flex flex-wrap items-center gap-2 mt-2">
              {showVendor && (
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <Store className="h-3.5 w-3.5" />
                  <span>{group.vendor_name}</span>
                </div>
              )}
              
              {showLocation && (
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5" />
                  <span>{group.area_name}</span>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col items-end gap-2">
            <Badge className={status.className}>
              {status.label}
            </Badge>
            
            {discountValue > 0 && (
              <Badge variant="outline" className="border-green-500 text-green-700">
                <Tag className="h-3 w-3 mr-1" />
                {discountValue}% OFF
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="pb-4" onClick={() => navigate(`/buying-groups/${group.id}`)}>
        <GroupProgress
          currentQuantity={group.current_quantity}
          targetQuantity={group.target_quantity}
          minQuantity={Math.floor(group.min_quantity)} 
          progressPercent={group.progress_percent}
          animate={false}
        />
      </CardContent>

      <CardFooter className="pt-3 border-t flex items-center justify-between">
        <CountdownTimer 
          expiresAt={group.expires_at}
          showBadge={true}
        />

        <Button 
          variant="ghost" 
          size="sm"
          onClick={() => navigate(`/buying-groups/${group.id}`)}
          className="group-hover:text-primary"
        >
          View Details
          <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
        </Button>
      </CardFooter>
    </Card>
  );
}