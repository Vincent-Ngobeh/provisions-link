// frontend/src/components/buying-groups/JoinGroupModal.tsx
// Modal for joining a buying group with quantity and postcode

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { buyingGroupsApi } from '@/api/endpoints';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, MapPin, Package, Tag, Info } from 'lucide-react';
import type { BuyingGroupDetail, GroupCommitment } from '@/types';

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
  const [quantity, setQuantity] = useState<number>(1);
  const [postcode, setPostcode] = useState<string>('');
  const [error, setError] = useState<string>('');
  
  const queryClient = useQueryClient();

  const commitMutation = useMutation({
    mutationFn: (data: { quantity: number; postcode: string }) =>
      buyingGroupsApi.commit(group.id, data),
    onSuccess: (response) => {
      // Invalidate queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['buying-group', group.id] });
      queryClient.invalidateQueries({ queryKey: ['buying-groups'] });
      
      // Close modal and notify parent with commitment data
      onOpenChange(false);
      if (onSuccess) {
        onSuccess(response.data.commitment);
      }
      
      // Reset form
      setQuantity(1);
      setPostcode('');
      setError('');
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

    if (!postcode.trim()) {
      setError('Please enter your postcode');
      return;
    }

    // UK postcode regex (basic validation)
    const postcodeRegex = /^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$/i;
    if (!postcodeRegex.test(postcode.trim())) {
      setError('Please enter a valid UK postcode');
      return;
    }

    commitMutation.mutate({ quantity, postcode: postcode.trim().toUpperCase() });
  };

  const discountedPrice = parseFloat(group.discounted_price);
  const totalPrice = discountedPrice * quantity;
  const savings = parseFloat(group.savings_per_unit) * quantity;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Join Buying Group</DialogTitle>
          <DialogDescription>
            Commit to purchasing {group.product.name} at a discounted price
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
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
            <p className="text-xs text-muted-foreground">
              Available: {group.product.stock_quantity} units
            </p>
          </div>

          {/* Postcode Input */}
          <div className="space-y-2">
            <Label htmlFor="postcode" className="flex items-center gap-2">
              <MapPin className="h-4 w-4" />
              Your Postcode
            </Label>
            <Input
              id="postcode"
              type="text"
              placeholder="e.g., SW1A 1AA"
              value={postcode}
              onChange={(e) => setPostcode(e.target.value)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Must be within {group.radius_km}km of {group.area_name}
            </p>
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
              Your card will be pre-authorized. Payment will only be captured if the group reaches its minimum quantity.
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
              onClick={() => onOpenChange(false)}
              disabled={commitMutation.isPending}
            >
              Cancel
            </Button>
            
            <Button 
              type="submit" 
              disabled={commitMutation.isPending}
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
                  Commit to Buy
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}