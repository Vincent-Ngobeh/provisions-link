import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useQuery, useMutation } from '@tanstack/react-query';
import apiClient from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import { ArrowLeft } from 'lucide-react';

interface AddressFormData {
  address_name: 'home' | 'work' | 'other';
  recipient_name: string;
  phone_number: string;
  line1: string;
  line2?: string;
  city: string;
  postcode: string;
  is_default: boolean;
}

export default function EditAddressPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { register, handleSubmit, formState: { errors }, setValue, reset } = useForm<AddressFormData>();

  const { data: address, isLoading } = useQuery({
    queryKey: ['address', id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/addresses/${id}/`);
      return data;
    },
    enabled: !!id,
  });

  useEffect(() => {
    if (address) {
      reset({
        address_name: address.address_name,
        recipient_name: address.recipient_name,
        phone_number: address.phone_number,
        line1: address.line1,
        line2: address.line2 || '',
        city: address.city,
        postcode: address.postcode,
        is_default: address.is_default,
      });
    }
  }, [address, reset]);

  const updateMutation = useMutation({
    mutationFn: async (data: AddressFormData) => {
      const response = await apiClient.patch(`/addresses/${id}/`, {
        ...data,
        country: 'GB',
      });
      return response.data;
    },
    onSuccess: () => {
      toast({
        title: 'Success',
        description: 'Address updated successfully',
      });
      navigate('/addresses');
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to update address',
        variant: 'destructive',
      });
    },
  });

  const onSubmit = (data: AddressFormData) => {
    updateMutation.mutate(data);
  };

  if (isLoading) {
    return (
      <div className="container mx-auto py-8 max-w-2xl">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/4"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 max-w-2xl">
      <Button
        variant="ghost"
        onClick={() => navigate('/addresses')}
        className="mb-4"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Addresses
      </Button>

      <Card>
        <CardHeader>
          <CardTitle>Edit Address</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="address_name">Address Type</Label>
                <Select
                  defaultValue={address?.address_name || 'home'}
                  onValueChange={(value) => setValue('address_name', value as any)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="home">Home</SelectItem>
                    <SelectItem value="work">Work</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="recipient_name">Recipient Name *</Label>
                <Input
                  {...register('recipient_name', { required: 'Recipient name is required' })}
                  placeholder="John Doe"
                />
                {errors.recipient_name && (
                  <p className="text-sm text-destructive">{errors.recipient_name.message}</p>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="phone_number">Phone Number *</Label>
              <Input
                {...register('phone_number', { 
                  required: 'Phone number is required',
                  pattern: {
                    value: /^(?:(?:\+44)|(?:0))[\d\s]{10,11}$/,
                    message: 'Invalid UK phone number'
                  }
                })}
                placeholder="+44 7700 900000"
              />
              {errors.phone_number && (
                <p className="text-sm text-destructive">{errors.phone_number.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="line1">Address Line 1 *</Label>
              <Input
                {...register('line1', { required: 'Address is required' })}
                placeholder="123 Main Street"
              />
              {errors.line1 && (
                <p className="text-sm text-destructive">{errors.line1.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="line2">Address Line 2 (Optional)</Label>
              <Input
                {...register('line2')}
                placeholder="Flat 4B"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="city">City *</Label>
                <Input
                  {...register('city', { required: 'City is required' })}
                  placeholder="London"
                />
                {errors.city && (
                  <p className="text-sm text-destructive">{errors.city.message}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="postcode">Postcode *</Label>
                <Input
                  {...register('postcode', { 
                    required: 'Postcode is required',
                    pattern: {
                      value: /^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$/i,
                      message: 'Invalid UK postcode'
                    }
                  })}
                  placeholder="SW1A 1AA"
                  onChange={(e) => e.target.value = e.target.value.toUpperCase()}
                />
                {errors.postcode && (
                  <p className="text-sm text-destructive">{errors.postcode.message}</p>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="is_default"
                defaultChecked={address?.is_default}
                onCheckedChange={(checked) => setValue('is_default', checked as boolean)}
              />
              <Label htmlFor="is_default">Set as default address</Label>
            </div>

            <div className="flex gap-4">
              <Button 
                type="button" 
                variant="outline" 
                onClick={() => navigate('/addresses')}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button 
                type="submit" 
                disabled={updateMutation.isPending}
                className="flex-1"
              >
                {updateMutation.isPending ? 'Updating...' : 'Update Address'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}