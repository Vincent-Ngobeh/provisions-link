import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCart } from '@/contexts/CartContext';
import { cartApi } from '@/api/endpoints';
import { CartItemCard } from '@/components/cart/CartItemCard';
import { CartSummary } from '@/components/cart/CartSummary';
import { EmptyCart } from '@/components/cart/EmptyCart';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { ShoppingCart, ArrowLeft, Trash2 } from 'lucide-react';

export default function CartPage() {
  const navigate = useNavigate();
  const { cart, isLoading, updateQuantity, removeItem, clearCart } = useCart();

 
  const { data: vendorSummary } = useQuery({
    queryKey: ['cart-summary'],
    queryFn: () => cartApi.getSummary(),
    enabled: !!cart && cart.items.length > 0,
  });

  if (isLoading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <Skeleton className="h-12 w-48 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (!cart || cart.items.length === 0) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-6xl">
        <EmptyCart />
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <ShoppingCart className="h-8 w-8 text-primary" />
            <h1 className="text-3xl font-bold">Shopping Cart</h1>
          </div>
          <p className="text-muted-foreground">
            {cart.items_count} {cart.items_count === 1 ? 'item' : 'items'} in your cart
          </p>
        </div>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline" size="sm">
              <Trash2 className="h-4 w-4 mr-2" />
              Clear Cart
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Clear Cart?</AlertDialogTitle>
              <AlertDialogDescription>
                This will remove all {cart.items_count} items from your cart. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={clearCart}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Clear Cart
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Cart Items */}
        <div className="lg:col-span-2 space-y-4">
          {cart.items.map((item) => (
            <CartItemCard
              key={item.id}
              item={item}
              onUpdateQuantity={updateQuantity}
              onRemove={removeItem}
            />
          ))}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <CartSummary cart={cart} vendorSummary={vendorSummary?.data} />

          <div className="space-y-3">
            <Button
              className="w-full"
              size="lg"
              onClick={() => navigate('/checkout')}
            >
              Proceed to Checkout
            </Button>

            <Button
              variant="outline"
              className="w-full"
              asChild
            >
              <Link to="/products">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Continue Shopping
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}