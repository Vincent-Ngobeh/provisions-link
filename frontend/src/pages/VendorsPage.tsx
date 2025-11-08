// frontend/src/pages/VendorsPage.tsx
// Public vendor listing page with search and location filters

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { vendorsApi } from '@/api/endpoints';
import { VendorCard } from '@/components/vendors/VendorCard';
import { Vendor } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Store,
  Search,
  MapPin,
  Filter,
  AlertCircle,
  TrendingUp,
  Award,
} from 'lucide-react';

export default function VendorsPage() {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [locationPostcode, setLocationPostcode] = useState('');
  const [minRating, setMinRating] = useState<string>('all');
  const [useLocationFilter, setUseLocationFilter] = useState(false);

  // Fetch all vendors or location-based vendors
  const { data: allVendorsData, isLoading: isLoadingAll } = useQuery({
    queryKey: ['vendors', searchQuery],
    queryFn: () => vendorsApi.list({ search: searchQuery }),
    enabled: !useLocationFilter,
  });

  const { data: locationData, isLoading: isLoadingLocation } = useQuery({
    queryKey: ['vendors-location', locationPostcode, minRating],
    queryFn: () =>
      vendorsApi.searchByLocation({
        postcode: locationPostcode,
        radius_km: 20,
        min_rating: minRating === 'all' ? undefined : parseInt(minRating),
      }),
    enabled: useLocationFilter && locationPostcode.length > 0,
  });

  const isLoading = useLocationFilter ? isLoadingLocation : isLoadingAll;
  
  // Get raw vendor data
  const rawVendors: Vendor[] = useLocationFilter
    ? locationData?.data?.vendors || []
    : allVendorsData?.data?.results || [];

  // Apply FSA rating filter client-side for name search
  const vendors: Vendor[] = !useLocationFilter && minRating !== 'all'
    ? rawVendors.filter(v => {
        const rating = v.fsa_rating_value;
        if (rating === null || rating === undefined) return false;
        const minRatingNum = parseInt(minRating);
        return rating >= minRatingNum;
      })
    : rawVendors;

  const handleLocationSearch = () => {
    if (locationPostcode.trim()) {
      setUseLocationFilter(true);
    }
  };

  const handleClearLocation = () => {
    setUseLocationFilter(false);
    setLocationPostcode('');
  };

  // Calculate statistics
  const stats = {
    total: vendors.length,
    verified: vendors.filter((v: Vendor) => v.fsa_rating_value !== null && v.fsa_rating_value !== undefined).length,
    avgRating:
      vendors.length > 0
        ? vendors.reduce((sum: number, v: Vendor) => sum + (v.fsa_rating_value || 0), 0) / vendors.filter(v => v.fsa_rating_value !== null).length || 0
        : 0,
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Store className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">Our Vendors</h1>
        </div>
        <p className="text-muted-foreground">
          Discover quality food suppliers verified by the Food Standards Agency
        </p>
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-full">
              <Store className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.total}</p>
              <p className="text-sm text-muted-foreground">Total Vendors</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-full">
              <Award className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.verified}</p>
              <p className="text-sm text-muted-foreground">FSA Verified</p>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-lg border p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-yellow-100 rounded-full">
              <TrendingUp className="h-5 w-5 text-yellow-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{stats.avgRating.toFixed(1)}</p>
              <p className="text-sm text-muted-foreground">Avg FSA Rating</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card rounded-lg border p-4 mb-6 space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Filter className="h-4 w-4" />
          Filters
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Search by Name */}
          {!useLocationFilter && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Search</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search vendors..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          )}

          {/* Location Search */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Near You</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Enter postcode"
                  value={locationPostcode}
                  onChange={(e) => setLocationPostcode(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && handleLocationSearch()}
                  className="pl-10"
                />
              </div>
              {useLocationFilter ? (
                <Button variant="outline" onClick={handleClearLocation}>
                  Clear
                </Button>
              ) : (
                <Button onClick={handleLocationSearch} disabled={!locationPostcode.trim()}>
                  <Search className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          {/* FSA Rating Filter */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Minimum FSA Rating</label>
            <Select value={minRating} onValueChange={setMinRating}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Ratings</SelectItem>
                <SelectItem value="5">5 Stars</SelectItem>
                <SelectItem value="4">4+ Stars</SelectItem>
                <SelectItem value="3">3+ Stars</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {useLocationFilter && locationData && (
          <p className="text-sm text-muted-foreground">
            Found {locationData.data.vendors.length} vendors within 20km of {locationPostcode}
          </p>
        )}
      </div>

      {/* Vendors Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : vendors.length === 0 ? (
        <div className="text-center py-12">
          <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No vendors found</h3>
          <p className="text-muted-foreground mb-4">
            {useLocationFilter
              ? 'Try a different location or increase the search radius'
              : 'No vendors match your search criteria'}
          </p>
          {(useLocationFilter || searchQuery) && (
            <Button
              variant="outline"
              onClick={() => {
                setUseLocationFilter(false);
                setSearchQuery('');
                setLocationPostcode('');
              }}
            >
              Clear All Filters
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {vendors.map((vendor: Vendor) => (
            <VendorCard
              key={vendor.id}
              vendor={vendor}
              onClick={() => navigate(`/vendors/${vendor.id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}