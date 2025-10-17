// frontend/src/pages/BuyingGroupsPage.tsx
// Page displaying all active buying groups

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { buyingGroupsApi } from '@/api/endpoints';
import { GroupCard } from '@/components/buying-groups/GroupCard';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  Users, 
  Search, 
  MapPin, 
  Filter, 
  AlertCircle,
  TrendingUp,
  Info
} from 'lucide-react';

export default function BuyingGroupsPage() {
  const [statusFilter, setStatusFilter] = useState<string>('open');
  const [searchPostcode, setSearchPostcode] = useState<string>('');
  const [useLocationFilter, setUseLocationFilter] = useState(false);

  // Fetch all groups or location-based groups
  const { data: allGroupsData, isLoading: isLoadingAll } = useQuery({
    queryKey: ['buying-groups', statusFilter],
    queryFn: () => buyingGroupsApi.list({ status: statusFilter, hide_expired: true }),
    enabled: !useLocationFilter,
  });

  const { data: nearbyData, isLoading: isLoadingNearby } = useQuery({
    queryKey: ['buying-groups-nearby', searchPostcode],
    queryFn: () => buyingGroupsApi.nearMe({ postcode: searchPostcode }),
    enabled: useLocationFilter && searchPostcode.length > 0,
  });

  const isLoading = useLocationFilter ? isLoadingNearby : isLoadingAll;
  const groups = useLocationFilter 
    ? nearbyData?.data?.groups || []
    : allGroupsData?.data?.results || [];

  const handleLocationSearch = () => {
    if (searchPostcode.trim()) {
      setUseLocationFilter(true);
    }
  };

  const handleClearLocation = () => {
    setUseLocationFilter(false);
    setSearchPostcode('');
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Users className="h-8 w-8 text-primary" />
          <h1 className="text-3xl font-bold">Buying Groups</h1>
        </div>
        <p className="text-muted-foreground">
          Join forces with other buyers to unlock group discounts on products
        </p>
      </div>

      {/* Info Alert */}
      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>How it works:</strong> When a group reaches its target quantity, everyone gets the discounted price. 
          Your card is only charged if the minimum quantity is reached.
        </AlertDescription>
      </Alert>

      {/* Filters */}
      <div className="bg-card rounded-lg border p-4 mb-6 space-y-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Filter className="h-4 w-4" />
          Filters
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Status Filter */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Status</label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="open">Active Groups</SelectItem>
                <SelectItem value="active">Target Reached</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Location Search */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Near You</label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Enter postcode (e.g., SW1A 1AA)"
                  value={searchPostcode}
                  onChange={(e) => setSearchPostcode(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleLocationSearch()}
                  className="pl-10"
                />
              </div>
              
              {useLocationFilter ? (
                <Button variant="outline" onClick={handleClearLocation}>
                  Clear
                </Button>
              ) : (
                <Button onClick={handleLocationSearch} disabled={!searchPostcode.trim()}>
                  <Search className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </div>

        {useLocationFilter && nearbyData && (
          <p className="text-sm text-muted-foreground">
            Found {nearbyData.data.count} groups within {nearbyData.data.radius_km}km of {nearbyData.data.location}
          </p>
        )}
      </div>

      {/* Stats Banner */}
      {!useLocationFilter && allGroupsData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-card rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-full">
                <Users className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{allGroupsData.data.count}</p>
                <p className="text-sm text-muted-foreground">Active Groups</p>
              </div>
            </div>
          </div>

          <div className="bg-card rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-full">
                <TrendingUp className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {Math.round(
                    groups.reduce((sum, g) => sum + g.progress_percent, 0) / groups.length || 0
                  )}%
                </p>
                <p className="text-sm text-muted-foreground">Avg Progress</p>
              </div>
            </div>
          </div>

          <div className="bg-card rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-100 rounded-full">
                <MapPin className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {new Set(groups.map(g => g.area_name)).size}
                </p>
                <p className="text-sm text-muted-foreground">Locations</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Groups Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="text-center py-12">
          <AlertCircle className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold mb-2">No buying groups found</h3>
          <p className="text-muted-foreground mb-4">
            {useLocationFilter 
              ? 'Try searching in a different location or expanding your radius'
              : 'Check back soon for new group buying opportunities'
            }
          </p>
          {useLocationFilter && (
            <Button variant="outline" onClick={handleClearLocation}>
              View All Groups
            </Button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {groups.map((group) => (
            <GroupCard key={group.id} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}