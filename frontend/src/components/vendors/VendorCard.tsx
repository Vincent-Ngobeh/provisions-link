// frontend/src/components/vendors/VendorCard.tsx
// Reusable vendor card for list views

import { Vendor } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { FSARatingBadge } from './FSARatingBadge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Store,
  MapPin,
  Package,
  TrendingUp,
  CheckCircle,
  ArrowRight,
} from 'lucide-react';

interface VendorCardProps {
  vendor: Vendor;
  onClick: () => void;
}

export function VendorCard({ vendor, onClick }: VendorCardProps) {
  return (
    <Card
      className="hover:shadow-lg transition-shadow cursor-pointer"
      onClick={onClick}
    >
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          {vendor.logo_url ? (
            <img
              src={vendor.logo_url}
              alt={vendor.business_name}
              className="w-16 h-16 rounded-lg object-cover border"
            />
          ) : (
            <div className="w-16 h-16 rounded-lg bg-muted flex items-center justify-center border">
              <Store className="h-8 w-8 text-muted-foreground" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-lg truncate mb-1">
              {vendor.business_name}
            </h3>
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
              <MapPin className="h-4 w-4" />
              <span>{vendor.postcode}</span>
              {vendor.distance_km && (
                <span className="text-xs">({vendor.distance_km}km away)</span>
              )}
            </div>
            {vendor.fsa_verified && (
              <Badge variant="outline" className="border-green-500 text-green-700">
                <CheckCircle className="h-3 w-3 mr-1" />
                FSA Verified
              </Badge>
            )}
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground line-clamp-2 mb-4">
          {vendor.description}
        </p>

        {/* Stats */}
        <div className="flex items-center gap-4 mb-4 text-sm">
          {vendor.products_count !== undefined && (
            <div className="flex items-center gap-2">
              <Package className="h-4 w-4 text-muted-foreground" />
              <span>{vendor.products_count} products</span>
            </div>
          )}
          {vendor.active_groups_count !== undefined && vendor.active_groups_count > 0 && (
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <span>{vendor.active_groups_count} active groups</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t">
          {vendor.fsa_rating_value ? (
            <FSARatingBadge rating={vendor.fsa_rating_value} />
          ) : (
            <span className="text-sm text-muted-foreground">No FSA rating</span>
          )}
          <Button variant="ghost" size="sm">
            View Profile
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}