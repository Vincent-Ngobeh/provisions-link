import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import axios from '@/lib/axios';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { MapPin, Plus, Home, Building } from 'lucide-react';

interface Address {
  id: number;
  address_name: string;
  recipient_name: string;
  phone_number: string;
  line1: string;
  line2: string;
  city: string;
  postcode: string;
  is_default: boolean;
}

export function AddressList() {
  const navigate = useNavigate();
  
  const { data: addresses, isLoading } = useQuery<Address[]>({
    queryKey: ['addresses'],
    queryFn: async () => {
      const { data } = await axios.get('/api/v1/addresses/');
      return data.results || data;
    },
  });

  const getAddressIcon = (type: string) => {
    switch (type) {
      case 'home':
        return <Home className="h-4 w-4" />;
      case 'work':
        return <Building className="h-4 w-4" />;
      default:
        return <MapPin className="h-4 w-4" />;
    }
  };

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2">
        <div className="h-16 bg-gray-200 rounded"></div>
        <div className="h-16 bg-gray-200 rounded"></div>
      </div>
    );
  }

  if (!addresses || addresses.length === 0) {
    return (
      <div className="text-center py-6">
        <MapPin className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
        <p className="text-muted-foreground mb-4">No addresses added yet</p>
        <Button onClick={() => navigate('/addresses/new')} size="sm">
          <Plus className="h-4 w-4 mr-2" />
          Add Your First Address
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {addresses.slice(0, 3).map((address) => (
        <div
          key={address.id}
          className="border rounded-lg p-3 hover:bg-muted/50 cursor-pointer transition-colors"
          onClick={() => navigate('/addresses')}
        >
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-2">
              {getAddressIcon(address.address_name)}
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-sm">{address.recipient_name}</p>
                  {address.is_default && (
                    <Badge variant="secondary" className="text-xs">
                      Default
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {address.line1}, {address.city} {address.postcode}
                </p>
              </div>
            </div>
          </div>
        </div>
      ))}
      
      {addresses.length > 3 && (
        <Button
          variant="ghost"
          className="w-full"
          onClick={() => navigate('/addresses')}
        >
          View all {addresses.length} addresses
        </Button>
      )}
    </div>
  );
}