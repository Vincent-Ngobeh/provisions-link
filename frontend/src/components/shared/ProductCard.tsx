// frontend/src/components/shared/ProductCard.tsx
import { Link } from 'react-router-dom';
import { Card, CardContent, CardFooter } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ShoppingCart, ArrowRight, Tag, CheckCircle2 } from 'lucide-react';
import { useCart } from '@/contexts/CartContext';
import { useAuth } from '@/contexts/AuthContext';
import type { Product } from '@/types';

interface ProductCardProps {
  product: Product;
}

export function ProductCard({ product }: ProductCardProps) {
  const { addToCart } = useCart();
  const { isAuthenticated } = useAuth();

  const handleAddToCart = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!isAuthenticated) {
      window.location.href = '/login';
      return;
    }
    
    try {
      await addToCart(product.id, 1);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  // Check if vendor is verified
  const isVendorVerified = product.vendor.is_approved && product.vendor.stripe_onboarding_complete;

  return (
    <Card className="overflow-hidden hover:shadow-lg transition-shadow flex flex-col h-full">
      <Link to={`/products/${product.id}`}>
        <div className="aspect-square overflow-hidden bg-gray-100">
          {product.primary_image ? (
            <img
              src={product.primary_image}
              alt={product.name}
              className="w-full h-full object-cover hover:scale-105 transition-transform"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400">
              No Image
            </div>
          )}
        </div>
      </Link>

      <CardContent className="pt-4 space-y-2 flex-1 flex flex-col">
        <Link to={`/products/${product.id}`}>
          <h3 className="font-semibold text-lg line-clamp-2 hover:text-primary">
            {product.name}
          </h3>
        </Link>

        <div className="flex items-center gap-2">
          <p className="text-sm text-muted-foreground">
            by {product.vendor.business_name}
          </p>
          {isVendorVerified && (
            <div className="relative group">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-2 py-1 text-xs text-white bg-gray-900 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                Verified Vendor
              </span>
            </div>
          )}
        </div>

        {/* Price and Stock Status */}
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-2xl font-bold text-primary">
                £{product.price}
              </span>
              <span className="text-xs text-muted-foreground">per {product.unit}</span>
            </div>
            {product.stock_quantity === 0 && (
              <Badge variant="destructive" className="text-xs">
                Out of Stock
              </Badge>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {product.contains_allergens && (
            <Badge variant="outline" className="text-xs">
              Contains Allergens
            </Badge>
          )}
          <Badge variant="secondary" className="text-xs">
            Min. order £{product.vendor.min_order_value}
          </Badge>
        </div>

        {/* Spacer to push group buy section and buttons to bottom */}
        <div className="flex-1"></div>

        {/* Group Buy Teaser - now at bottom */}
        {product.active_group && (
          <Link to={`/buying-groups/${product.active_group.id}`}>
            <div className="p-3 bg-gradient-to-r from-green-50 to-blue-50 border border-green-200 rounded-md hover:shadow-md transition-all cursor-pointer group">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Tag className="h-4 w-4 text-green-600" />
                    <span className="font-semibold text-green-700 text-sm">
                      Group Buy Available
                    </span>
                  </div>
                  <p className="text-xs text-green-600 mb-1">
                    Save {product.active_group.discount_percent}% when target reached
                  </p>
                  <div className="text-xs text-muted-foreground">
                    {product.active_group.current_quantity}/{product.active_group.target_quantity} committed • {Math.round((product.active_group.current_quantity / product.active_group.target_quantity) * 100)}% progress
                  </div>
                </div>
                <ArrowRight className="h-5 w-5 text-green-600 shrink-0 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </Link>
        )}
      </CardContent>

      <CardFooter className="pt-0 flex gap-2 mt-auto">
        <Button
          className="flex-1"
          variant="outline"
          disabled={!product.in_stock || !isVendorVerified}
          onClick={handleAddToCart}
        >
          {!isVendorVerified ? (
            'Vendor Not Verified'
          ) : product.in_stock ? (
            <>
              <ShoppingCart className="mr-2 h-4 w-4" />
              Add to Cart
            </>
          ) : (
            'Out of Stock'
          )}
        </Button>
        
        <Button
          className="flex-1"
          disabled={!product.in_stock}
          asChild={product.in_stock}
        >
          {product.in_stock ? (
            <Link to={`/products/${product.id}`}>View Details</Link>
          ) : (
            <>Out of Stock</>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}