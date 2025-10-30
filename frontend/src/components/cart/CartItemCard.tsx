import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Minus, Plus, Trash2, Loader2 } from 'lucide-react';
import type { CartItem } from '@/types';

interface CartItemCardProps {
  item: CartItem;
  onUpdateQuantity: (itemId: number, quantity: number) => Promise<void>;
  onRemove: (itemId: number) => Promise<void>;
}

export function CartItemCard({ item, onUpdateQuantity, onRemove }: CartItemCardProps) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [quantity, setQuantity] = useState(item.quantity);

  const handleQuantityChange = async (newQuantity: number) => {
    if (newQuantity < 1) return;
    if (newQuantity > item.product.stock_quantity) {
      alert(`Only ${item.product.stock_quantity} units available`);
      return;
    }

    setQuantity(newQuantity);
    setIsUpdating(true);
    try {
      await onUpdateQuantity(item.id, newQuantity);
    } catch (error) {
      setQuantity(item.quantity); // Revert on error
    } finally {
      setIsUpdating(false);
    }
  };

  const handleRemove = async () => {
    setIsUpdating(true);
    try {
      await onRemove(item.id);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex gap-4">
          {/* Product Image */}
          <Link to={`/products/${item.product.id}`} className="shrink-0">
            {item.product.primary_image ? (
              <img
                src={item.product.primary_image}
                alt={item.product.name}
                className="w-24 h-24 object-cover rounded"
              />
            ) : (
              <div className="w-24 h-24 bg-gray-100 rounded flex items-center justify-center text-gray-400">
                No Image
              </div>
            )}
          </Link>

          {/* Product Details */}
          <div className="flex-1 min-w-0">
            <Link
              to={`/products/${item.product.id}`}
              className="font-semibold hover:text-primary line-clamp-2"
            >
              {item.product.name}
            </Link>
            
            <p className="text-sm text-muted-foreground mt-1">
              by {item.product.vendor.business_name}
            </p>

            <div className="flex items-center gap-2 mt-2">
              <span className="text-lg font-bold">£{item.product.price}</span>
              <span className="text-sm text-muted-foreground">per {item.product.unit}</span>
            </div>

            {!item.product.in_stock && (
              <p className="text-sm text-red-600 mt-1">Out of stock</p>
            )}
          </div>

          {/* Quantity Controls */}
          <div className="flex flex-col items-end gap-2">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => handleQuantityChange(quantity - 1)}
                disabled={isUpdating || quantity <= 1}
              >
                <Minus className="h-4 w-4" />
              </Button>

              <Input
                type="number"
                min="1"
                max={item.product.stock_quantity}
                value={quantity}
                onChange={(e) => {
                  const newQty = parseInt(e.target.value) || 1;
                  handleQuantityChange(newQty);
                }}
                className="w-16 text-center"
                disabled={isUpdating}
              />

              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8"
                onClick={() => handleQuantityChange(quantity + 1)}
                disabled={isUpdating || quantity >= item.product.stock_quantity}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            <div className="text-right">
              <p className="text-sm text-muted-foreground">Subtotal</p>
              <p className="text-lg font-bold">
                £{parseFloat(item.total_with_vat).toFixed(2)}
              </p>
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleRemove}
              disabled={isUpdating}
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              {isUpdating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-1" />
                  Remove
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}