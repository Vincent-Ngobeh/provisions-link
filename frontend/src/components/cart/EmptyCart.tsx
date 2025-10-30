import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ShoppingCart } from 'lucide-react';

export function EmptyCart() {
  return (
    <div className="text-center py-16">
      <div className="flex justify-center mb-6">
        <div className="p-6 bg-gray-100 rounded-full">
          <ShoppingCart className="h-16 w-16 text-gray-400" />
        </div>
      </div>
      
      <h2 className="text-2xl font-bold mb-2">Your cart is empty</h2>
      <p className="text-muted-foreground mb-8">
        Add some products to get started
      </p>
      
      <div className="flex gap-4 justify-center">
        <Button asChild>
          <Link to="/products">Browse Products</Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/buying-groups">View Group Buys</Link>
        </Button>
      </div>
    </div>
  );
}