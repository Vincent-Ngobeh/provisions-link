// frontend/src/components/buying-groups/JoinGroupModal.tsx
import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { buyingGroupsApi, addressesApi } from '@/api/endpoints';
import { loadStripe } from '@stripe/stripe-js';
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { 
  Loader2, 
  MapPin, 
  Package, 
  Tag, 
  Info, 
  AlertCircle, 
  Plus,
  Users,
  Clock,
  Navigation,
  TrendingUp
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { BuyingGroupDetail, GroupCommitment } from '@/types';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '');

interface JoinGroupModalProps {
  group: BuyingGroupDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (commitment: GroupCommitment) => void;
}

export function JoinGroupModal({
  group,
  open,
  onOpenChange,
  onSuccess,
}: JoinGroupModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Join Buying Group</DialogTitle>
          <DialogDescription>
            Commit to purchasing {group.product.name} at a discounted price
          </DialogDescription>
        </DialogHeader>

        <JoinGroupForm
          group={group}
          onSuccess={(commitment) => {
            onOpenChange(false);
            if (onSuccess) onSuccess(commitment);
          }}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function JoinGroupForm({
  group,
  onSuccess,
  onCancel,
}: {
  group: BuyingGroupDetail;
  onSuccess: (commitment: GroupCommitment) => void;
  onCancel: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [quantity, setQuantity] = useState<number>(1);
  const [postcode, setPostcode] = useState<string>('');
  const [selectedAddressId, setSelectedAddressId] = useState<string>('');
  const [deliveryNotes, setDeliveryNotes] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [clientSecret, setClientSecret] = useState<string | null>(null);
  const [showAddressForm, setShowAddressForm] = useState<boolean>(false);
  const [isValidatingAddress, setIsValidatingAddress] = useState<boolean>(false);

  // Fetch addresses
  const { data: addressesData, isLoading: isLoadingAddresses } = useQuery({
    queryKey: ['addresses'],
    queryFn: () => addressesApi.list(),
  });

  const addresses = addressesData?.data?.results || [];
  const defaultAddress = addresses.find((a: any) => a.is_default);

  // Auto-select default address and validate it
  useEffect(() => {
    if (defaultAddress && !selectedAddressId && !showAddressForm) {
      handleAddressSelection(defaultAddress.id.toString());
    }
  }, [defaultAddress, selectedAddressId, showAddressForm]);

  // Validate address is within radius
  const validateAddressMutation = useMutation({
    mutationFn: async (addressId: number) => {
      const response = await buyingGroupsApi.validateAddress(group.id, addressId);
      return response.data;
    },
  });

  const handleAddressSelection = async (addressId: string) => {
    const addr = addresses.find((a: any) => a.id.toString() === addressId);
    if (!addr) return;

    setIsValidatingAddress(true);
    setError('');

    try {
      const result = await validateAddressMutation.mutateAsync(addr.id);
      
      if (result.valid) {
        setSelectedAddressId(addressId);
        setPostcode(addr.postcode);
        setError('');
      } else {
        setError(
          `This address is ${result.distance_km}km from the group center. ` +
          `Maximum allowed distance is ${result.max_distance_km}km. ` +
          `Please select a different address or create a new one within the delivery area.`
        );
        setSelectedAddressId('');
        setPostcode('');
      }
    } catch (err: any) {
      setError('Failed to validate address. Please try again.');
    } finally {
      setIsValidatingAddress(false);
    }
  };

  const commitMutation = useMutation({
    mutationFn: async (data: { 
      quantity: number; 
      postcode: string;
      delivery_address_id: number;
      delivery_notes?: string;
    }) => {
      const response = await buyingGroupsApi.commit(group.id, data);
      return response;
    },
    onSuccess: (response) => {
      // Check if payment is needed
      const paymentIntent = response.data.payment_intent;
      
      if (paymentIntent?.client_secret) {
        // Set client secret to show payment form
        setClientSecret(paymentIntent.client_secret);
      } else {
        // No payment needed, complete immediately
        queryClient.invalidateQueries({ queryKey: ['buying-group', group.id] });
        queryClient.invalidateQueries({ queryKey: ['buying-groups'] });
        onSuccess(response.data.commitment);
      }
    },
    onError: (error: any) => {
      const message = error.response?.data?.error || 'Failed to join group. Please try again.';
      setError(message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Validation
    if (quantity < 1) {
      setError('Quantity must be at least 1');
      return;
    }

    if (!selectedAddressId) {
      setError('Please select a delivery address');
      return;
    }

    if (!postcode.trim()) {
      setError('Please enter your delivery postcode');
      return;
    }

    commitMutation.mutate({
      quantity,
      postcode: postcode.trim().toUpperCase(),
      delivery_address_id: parseInt(selectedAddressId),
      delivery_notes: deliveryNotes || undefined,
    });
  };

  const discountedPrice = parseFloat(group.discounted_price);
  const totalPrice = discountedPrice * quantity;
  const savings = parseFloat(group.savings_per_unit) * quantity;

  // Calculate time remaining
  const getTimeRemaining = () => {
    const now = new Date();
    const expiresAt = new Date(group.expires_at);
    const diffMs = expiresAt.getTime() - now.getTime();
    
    if (diffMs <= 0) return 'Expired';
    
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (days > 0) {
      return `${days} day${days !== 1 ? 's' : ''} ${hours}h remaining`;
    }
    return `${hours} hour${hours !== 1 ? 's' : ''} remaining`;
  };

  if (isLoadingAddresses) {
    return <Skeleton className="h-96" />;
  }

  // If payment is needed, show payment form
  if (clientSecret) {
    return (
      <Elements stripe={stripePromise} options={{ clientSecret }}>
        <PaymentForm
          group={group}
          quantity={quantity}
          totalPrice={totalPrice}
          clientSecret={clientSecret}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ['buying-group', group.id] });
            queryClient.invalidateQueries({ queryKey: ['buying-groups'] });
            onSuccess(commitMutation.data!.data.commitment);
          }}
          onCancel={() => setClientSecret(null)}
        />
      </Elements>
    );
  }

  // Show inline address creation form
  if (showAddressForm) {
    return (
      <InlineAddressForm
        groupId={group.id}
        radiusKm={group.radius_km}
        onSuccess={(newAddress) => {
          setShowAddressForm(false);
          queryClient.invalidateQueries({ queryKey: ['addresses'] });
          // Address will be auto-selected via useEffect after addresses refresh
        }}
        onCancel={() => setShowAddressForm(false)}
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Group Context Info - MODIFIED */}
      <div className="rounded-lg border bg-muted/30 p-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-start gap-2">
            <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground">Location</p>
              <p className="text-sm font-medium">{group.area_name}</p>
              <p className="text-xs text-muted-foreground">
                {group.product.vendor.postcode || 'Postcode N/A'} • Within {group.radius_km}km
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground">Time Left</p>
              <p className="text-sm font-medium">{getTimeRemaining()}</p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <TrendingUp className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground">Progress</p>
              <p className="text-sm font-medium">
                {group.current_quantity}/{group.target_quantity} units
              </p>
              <p className="text-xs text-muted-foreground">
                {group.progress_percent.toFixed(0)}% complete
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2">
            <Users className="h-4 w-4 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-xs text-muted-foreground">Participants</p>
              <p className="text-sm font-medium">{group.participants_count} buyers</p>
            </div>
          </div>
        </div>
      </div>

      <Separator />

      {/* Product Info */}
      <div className="rounded-lg bg-muted p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Product</span>
          <span className="font-medium">{group.product.name}</span>
        </div>
        
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Discounted Price</span>
          <div className="flex items-center gap-2">
            <span className="text-sm line-through text-muted-foreground">
              £{group.product.price}
            </span>
            <span className="font-medium text-green-600">
              £{discountedPrice.toFixed(2)}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Discount</span>
          <span className="font-medium text-green-600">
            {group.discount_percent}% OFF
          </span>
        </div>
      </div>

      {/* Quantity Input */}
      <div className="space-y-2">
        <Label htmlFor="quantity" className="flex items-center gap-2">
          <Package className="h-4 w-4" />
          Quantity
        </Label>
        <Input
          id="quantity"
          type="number"
          min="1"
          value={quantity}
          onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
          required
        />
      </div>

      {/* Delivery Address */}
      <div className="space-y-2">
        <Label htmlFor="address" className="flex items-center gap-2">
          <MapPin className="h-4 w-4" />
          Delivery Address
        </Label>
        
        {addresses.length === 0 ? (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              No delivery address found. Please add an address to continue.
            </AlertDescription>
          </Alert>
        ) : (
          <Select 
            value={selectedAddressId} 
            onValueChange={handleAddressSelection}
            disabled={isValidatingAddress}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select delivery address" />
            </SelectTrigger>
            <SelectContent>
              {addresses.map((address: any) => (
                <SelectItem key={address.id} value={address.id.toString()}>
                  {address.recipient_name} - {address.line1}, {address.postcode}
                  {address.is_default && ' (Default)'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => setShowAddressForm(true)}
        >
          <Plus className="h-4 w-4 mr-2" />
          Add New Address
        </Button>

        {isValidatingAddress && (
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            <Loader2 className="h-3 w-3 animate-spin" />
            Validating address is within delivery area...
          </p>
        )}
      </div>

      {/* Delivery Postcode (Auto-filled from address) */}
      <div className="space-y-2">
        <Label htmlFor="postcode">Delivery Postcode</Label>
        <Input
          id="postcode"
          type="text"
          value={postcode}
          onChange={(e) => setPostcode(e.target.value)}
          placeholder="Auto-filled from address"
          required
          disabled
        />
        <p className="text-xs text-muted-foreground">
          Must be within {group.radius_km}km of {group.area_name}
        </p>
      </div>

      {/* Delivery Notes */}
      <div className="space-y-2">
        <Label htmlFor="notes">Delivery Notes (Optional)</Label>
        <Textarea
          id="notes"
          placeholder="e.g., Leave at reception, Call on arrival..."
          value={deliveryNotes}
          onChange={(e) => setDeliveryNotes(e.target.value)}
          rows={2}
        />
      </div>

      {/* Order Summary */}
      <div className="rounded-lg border p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm">Quantity</span>
          <span className="font-medium">{quantity} units</span>
        </div>
        
        <div className="flex items-center justify-between text-green-600">
          <span className="text-sm">Savings</span>
          <span className="font-medium">-£{savings.toFixed(2)}</span>
        </div>

        <div className="pt-2 border-t flex items-center justify-between">
          <span className="font-medium">Total</span>
          <span className="text-xl font-bold">£{totalPrice.toFixed(2)}</span>
        </div>
      </div>

      {/* Info Alert */}
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-xs">
          Your card will be charged when you confirm. Payment will only be captured if the group reaches its minimum quantity.
        </AlertDescription>
      </Alert>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={commitMutation.isPending}
        >
          Cancel
        </Button>
        
        <Button 
          type="submit" 
          disabled={commitMutation.isPending || !selectedAddressId || isValidatingAddress}
          className="gap-2"
        >
          {commitMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing...
            </>
          ) : (
            <>
              <Tag className="h-4 w-4" />
              Continue to Payment
            </>
          )}
        </Button>
      </DialogFooter>
    </form>
  );
}

function InlineAddressForm({
  groupId,
  radiusKm,
  onSuccess,
  onCancel,
}: {
  groupId: number;
  radiusKm: number;
  onSuccess: (address: any) => void;
  onCancel: () => void;
}) {
  const [formData, setFormData] = useState({
    recipient_name: '',
    line1: '',
    line2: '',
    city: '',
    postcode: '',
    phone: '',
    is_default: false,
  });
  const [error, setError] = useState<string>('');

  const createAddressMutation = useMutation({
    mutationFn: async (data: any) => {
      // First validate the address is in radius
      const tempAddr = { postcode: data.postcode };
      
      // Create the address
      const response = await addressesApi.create(data);
      
      // Validate it's in radius
      try {
        const validationResponse = await buyingGroupsApi.validateAddress(groupId, response.data.id);
        
        if (!validationResponse.data.valid) {
          // Delete the address we just created since it's invalid
          await addressesApi.delete(response.data.id);
          
          throw new Error(
            `This address is ${validationResponse.data.distance_km}km from the group center. ` +
            `Maximum allowed is ${radiusKm}km. Please use an address within the delivery area.`
          );
        }
      } catch (err: any) {
        // Delete the address if validation failed
        await addressesApi.delete(response.data.id);
        throw err;
      }
      
      return response.data;
    },
    onSuccess: (newAddress) => {
      onSuccess(newAddress);
    },
    onError: (err: any) => {
      const message = err.message || err.response?.data?.error || 'Failed to create address';
      setError(message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    // Basic validation
    if (!formData.recipient_name || !formData.line1 || !formData.city || !formData.postcode) {
      setError('Please fill in all required fields');
      return;
    }

    createAddressMutation.mutate(formData);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-xs">
          Address must be within {radiusKm}km of the group delivery area
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <Label htmlFor="recipient_name">Recipient Name *</Label>
          <Input
            id="recipient_name"
            value={formData.recipient_name}
            onChange={(e) => setFormData({ ...formData, recipient_name: e.target.value })}
            required
          />
        </div>

        <div className="col-span-2">
          <Label htmlFor="line1">Address Line 1 *</Label>
          <Input
            id="line1"
            value={formData.line1}
            onChange={(e) => setFormData({ ...formData, line1: e.target.value })}
            placeholder="123 Main Street"
            required
          />
        </div>

        <div className="col-span-2">
          <Label htmlFor="line2">Address Line 2</Label>
          <Input
            id="line2"
            value={formData.line2}
            onChange={(e) => setFormData({ ...formData, line2: e.target.value })}
            placeholder="Apt 4B (optional)"
          />
        </div>

        <div>
          <Label htmlFor="city">City *</Label>
          <Input
            id="city"
            value={formData.city}
            onChange={(e) => setFormData({ ...formData, city: e.target.value })}
            required
          />
        </div>

        <div>
          <Label htmlFor="postcode">Postcode *</Label>
          <Input
            id="postcode"
            value={formData.postcode}
            onChange={(e) => setFormData({ ...formData, postcode: e.target.value.toUpperCase() })}
            placeholder="SW1A 1AA"
            required
          />
        </div>

        <div className="col-span-2">
          <Label htmlFor="phone">Phone Number</Label>
          <Input
            id="phone"
            type="tel"
            value={formData.phone}
            onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
            placeholder="+44 7700 900000"
          />
        </div>

        <div className="col-span-2 flex items-center space-x-2">
          <input
            type="checkbox"
            id="is_default"
            checked={formData.is_default}
            onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
            className="h-4 w-4"
          />
          <Label htmlFor="is_default" className="font-normal">
            Set as default address
          </Label>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={createAddressMutation.isPending}
        >
          Back
        </Button>
        
        <Button 
          type="submit" 
          disabled={createAddressMutation.isPending}
        >
          {createAddressMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Creating...
            </>
          ) : (
            'Create & Use Address'
          )}
        </Button>
      </DialogFooter>
    </form>
  );
}

function PaymentForm({
  group,
  quantity,
  totalPrice,
  clientSecret,
  onSuccess,
  onCancel,
}: {
  group: BuyingGroupDetail;
  quantity: number;
  totalPrice: number;
  clientSecret: string;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [error, setError] = useState<string>('');
  const [isProcessing, setIsProcessing] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!stripe || !elements) {
      return;
    }

    setIsProcessing(true);
    setError('');

    const { error: submitError } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/buying-groups`,
      },
      redirect: 'if_required',
    });

    if (submitError) {
      setError(submitError.message || 'Payment failed');
      setIsProcessing(false);
    } else {
      onSuccess();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Order Summary */}
      <div className="rounded-lg border p-4 space-y-3">
        <h3 className="font-semibold">Order Summary</h3>
        
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Product</span>
            <span className="font-medium">{group.product.name}</span>
          </div>
          
          <div className="flex justify-between">
            <span className="text-muted-foreground">Quantity</span>
            <span className="font-medium">{quantity} units</span>
          </div>
          
          <div className="flex justify-between">
            <span className="text-muted-foreground">Price per unit</span>
            <span className="font-medium">£{parseFloat(group.discounted_price).toFixed(2)}</span>
          </div>

          <Separator />

          <div className="flex justify-between font-bold text-lg pt-1">
            <span>Total</span>
            <span className="text-primary">£{totalPrice.toFixed(2)}</span>
          </div>
        </div>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription className="text-xs">
          Your card will be pre-authorized. Funds will only be captured if the group succeeds.
        </AlertDescription>
      </Alert>

      <PaymentElement />

      {/* Test Card Info */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
        <p className="text-xs text-yellow-800 font-medium mb-1">
          🧪 Test Mode
        </p>
        <p className="text-xs text-yellow-700">
          Use test card: <code className="font-mono bg-yellow-100 px-1 rounded">4242 4242 4242 4242</code>
        </p>
        <p className="text-xs text-yellow-700 mt-1">
          Any CVC, future expiry date
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isProcessing}
        >
          Back
        </Button>
        
        <Button 
          type="submit" 
          disabled={!stripe || isProcessing}
        >
          {isProcessing ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Processing...
            </>
          ) : (
            'Confirm Payment'
          )}
        </Button>
      </DialogFooter>
    </form>
  );
}