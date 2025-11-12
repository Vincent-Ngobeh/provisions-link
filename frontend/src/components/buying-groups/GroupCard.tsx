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

  const getStatusConfig = () => {
    const isTargetReached = group.current_quantity >= group.target_quantity;
    const isMinReached = group.current_quantity >= group.min_quantity;
    
    if (group.status === 'open') {
      if (isTargetReached) {
        return { label: 'Target Reached ✓', className: 'bg-green-600 text-white hover:bg-green-700' };
      } else if (isMinReached) {
        return { label: 'Active - Min Reached', className: 'bg-blue-600 text-white hover:bg-blue-700' };
      } else {
        return { label: 'Active', className: 'bg-green-600 text-white hover:bg-green-700' };
      }
    }
    
    const statusConfig = {
      active: { label: 'Finalizing', className: 'bg-purple-600 text-white hover:bg-purple-700' },
      failed: { label: 'Failed', className: 'bg-red-600 text-white hover:bg-red-700' },
      completed: { label: 'Completed', className: 'bg-gray-600 text-white hover:bg-gray-700' },
    };
    
    return statusConfig[group.status as keyof typeof statusConfig] || { label: 'Active', className: 'bg-green-600 text-white hover:bg-green-700' };
  };

  const status = getStatusConfig();
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
          size="sm" 
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/buying-groups/${group.id}`);
          }}
          className="group-hover:translate-x-1 transition-transform"
        >
          View Details
          <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </CardFooter>
    </Card>
  );
}