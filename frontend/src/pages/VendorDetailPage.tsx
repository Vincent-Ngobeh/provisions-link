// frontend/src/pages/VendorDetailPage.tsx
// Public vendor profile page

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { vendorsApi, productsApi, buyingGroupsApi } from '@/api/endpoints';
import { FSARatingBadge } from '@/components/vendors/FSARatingBadge';
import { ProductCard } from '@/components/shared/ProductCard';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft,
  Store,
  MapPin,
  Phone,
  Package,
  Calendar,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';

export default function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // Fetch vendor details
  const { data: vendorData, isLoading: isLoadingVendor } = useQuery({
    queryKey: ['vendor', id],
    queryFn: () => vendorsApi.get(parseInt(id!)),
    enabled: !!id,
  });

  // Fetch vendor's products
  const { data: productsData, isLoading: isLoadingProducts } = useQuery({
    queryKey: ['vendor-products', id],
    queryFn: () => productsApi.list({ vendor: parseInt(id!) }),
    enabled: !!id,
  });

  // Fetch vendor's active buying groups
  const { data: buyingGroupsData } = useQuery({
    queryKey: ['vendor-buying-groups', id],
    queryFn: async () => {
      const response = await buyingGroupsApi.list({ status: 'open' });
      // Filter groups for this vendor's products
      const allGroups = response.data?.results || [];
      return allGroups.filter((group: any) => 
        group.vendor_name === vendorData?.data?.business_name
      );
    },
    enabled: !!id && !!vendorData?.data,
  });

  const vendor = vendorData?.data;
  const products = productsData?.data?.results || [];

  if (isLoadingVendor) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <Skeleton className="h-12 w-32 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Skeleton className="lg:col-span-2 h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }

  if (!vendor) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-2xl font-bold mb-2">Vendor Not Found</h2>
        <p className="text-muted-foreground mb-4">
          This vendor doesn't exist or is not available.
        </p>
        <Button onClick={() => navigate('/vendors')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Vendors
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Back Button */}
      <Button variant="ghost" onClick={() => navigate('/vendors')} className="mb-6">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Vendors
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Vendor Header */}
          <Card>
            <CardHeader>
              <div className="flex items-start gap-4">
                {vendor.logo_url ? (
                  <img
                    src={vendor.logo_url}
                    alt={vendor.business_name}
                    className="w-20 h-20 rounded-lg object-cover border"
                  />
                ) : (
                  <div className="w-20 h-20 rounded-lg bg-muted flex items-center justify-center border">
                    <Store className="h-10 w-10 text-muted-foreground" />
                  </div>
                )}
                <div className="flex-1">
                  <div className="flex items-start justify-between mb-2">
                    <h1 className="text-2xl font-bold">{vendor.business_name}</h1>
                    <div className="flex gap-2">
                      {vendor.fsa_verified && (
                        <Badge className="bg-green-100 text-green-800">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          FSA Verified
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <MapPin className="h-4 w-4" />
                      <span>{vendor.postcode}</span>
                    </div>
                    {vendor.phone_number && (
                      <div className="flex items-center gap-2">
                        <Phone className="h-4 w-4" />
                        <span>{vendor.phone_number}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground leading-relaxed">{vendor.description}</p>
            </CardContent>
          </Card>

          {/* Products */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Package className="h-5 w-5" />
                Products ({products.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoadingProducts ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[...Array(4)].map((_, i) => (
                    <Skeleton key={i} className="h-48" />
                  ))}
                </div>
              ) : products.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No products available at the moment
                </p>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {products.map((product) => (
                    <div
                      key={product.id}
                      onClick={() => navigate(`/products/${product.id}`)}
                      className="cursor-pointer"
                    >
                      <ProductCard product={product} />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* FSA Rating */}
          {vendor.fsa_rating_value && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Food Hygiene Rating</CardTitle>
              </CardHeader>
              <CardContent>
                <FSARatingBadge rating={vendor.fsa_rating_value} size="large" />
                {vendor.fsa_rating_date && (
                  <p className="text-sm text-muted-foreground mt-4">
                    Last inspected:{' '}
                    {new Date(vendor.fsa_rating_date).toLocaleDateString('en-GB', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Business Details */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Business Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Delivery Radius</p>
                <p className="font-medium">{vendor.delivery_radius_km} km</p>
              </div>

              <Separator />

              <div>
                <p className="text-sm text-muted-foreground mb-1">Minimum Order</p>
                <p className="font-medium">£{parseFloat(vendor.min_order_value).toFixed(2)}</p>
              </div>

              {vendor.created_at && (
                <>
                  <Separator />

                  <div>
                    <p className="text-sm text-muted-foreground mb-1">Member Since</p>
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      <span className="font-medium">
                        {new Date(vendor.created_at).toLocaleDateString('en-GB', {
                          month: 'long',
                          year: 'numeric',
                        })}
                      </span>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Statistics */}
          {(vendor.products_count !== undefined || vendor.active_groups_count !== undefined) && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Statistics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {vendor.products_count !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Products</span>
                    <Badge variant="secondary">{vendor.products_count}</Badge>
                  </div>
                )}

                {vendor.active_groups_count !== undefined && vendor.active_groups_count > 0 && (
                  <div 
                    className="flex justify-between items-center cursor-pointer hover:bg-accent rounded p-2 -m-2 transition-colors"
                    onClick={() => {
                      const groups = buyingGroupsData || [];
                      if (groups.length > 0) {
                        navigate(`/buying-groups/${groups[0].id}`);
                      } else {
                        navigate('/buying-groups');
                      }
                    }}
                  >
                    <span className="text-sm text-muted-foreground">Active Group Buys</span>
                    <Badge variant="secondary" className="cursor-pointer">
                      {vendor.active_groups_count}
                    </Badge>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}