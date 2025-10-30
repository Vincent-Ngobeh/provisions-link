import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { productsApi } from '@/api/endpoints';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { 
  ArrowLeft, 
  ShoppingCart, 
  Package, 
  AlertTriangle,
  MapPin,
  Star,
  Users
} from 'lucide-react';
import { useCart } from '@/contexts/CartContext';
import { useAuth } from '@/contexts/AuthContext';

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { isAuthenticated } = useAuth();

  const { data: product, isLoading, error } = useQuery({
    queryKey: ['product', id],
    queryFn: () => productsApi.get(Number(id)),
    enabled: !!id,
  });

  const handleAddToCart = async () => {
    if (!isAuthenticated) {
      navigate('/login');
      return;
    }
    
    try {
      await addToCart(productData.id, 1);
    } catch (error) {
      console.error('Failed to add to cart:', error);
    }
  };

  if (isLoading) {
    return <ProductDetailSkeleton />;
  }

  if (error || !product) {
    return (
      <div className="container mx-auto py-8">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            Failed to load product. Please try again later.
          </AlertDescription>
        </Alert>
        <Button 
          variant="outline" 
          onClick={() => navigate('/products')}
          className="mt-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Products
        </Button>
      </div>
    );
  }

  const productData = product.data;

  return (
    <div className="container mx-auto py-8 space-y-8">
      {/* Back Button */}
      <Button 
        variant="ghost" 
        onClick={() => navigate('/products')}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Products
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left Column - Images */}
        <div className="space-y-4">
          {/* Main Image */}
          <div className="aspect-square overflow-hidden rounded-lg border bg-gray-100">
            {productData.primary_image ? (
              <img
                src={productData.primary_image}
                alt={productData.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-gray-400">
                <Package className="h-24 w-24" />
              </div>
            )}
          </div>

          {/* Additional Images */}
          {productData.additional_images.length > 0 && (
            <div className="grid grid-cols-4 gap-2">
              {productData.additional_images.map((img, idx) => (
                <div 
                  key={idx}
                  className="aspect-square overflow-hidden rounded border bg-gray-100 cursor-pointer hover:border-primary"
                >
                  <img
                    src={img}
                    alt={`${productData.name} ${idx + 1}`}
                    className="w-full h-full object-cover"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column - Details */}
        <div className="space-y-6">
          {/* Title & Vendor */}
          <div>
            <h1 className="text-3xl font-bold mb-2">{productData.name}</h1>
            <Link 
              to={`/vendors/${productData.vendor.id}`}
              className="text-muted-foreground hover:text-primary"
            >
              by {productData.vendor.business_name}
            </Link>
          </div>

          {/* Tags */}
          {productData.tags && productData.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {productData.tags.map((tag) => (
                <Badge key={tag.id} variant="secondary">
                  {tag.name}
                </Badge>
              ))}
            </div>
          )}

          {/* Price */}
          <div className="space-y-1">
            <div className="flex items-baseline gap-2">
              <span className="text-4xl font-bold">£{productData.price}</span>
              <span className="text-muted-foreground">per {productData.unit}</span>
            </div>
            <p className="text-sm text-muted-foreground">
              £{productData.price_with_vat} inc. VAT
            </p>
          </div>

          {/* Stock Status */}
          <div className="flex items-center gap-2">
            <Package className="h-5 w-5" />
            {productData.in_stock ? (
              <span className="text-green-600 font-medium">
                In Stock ({productData.stock_quantity} {productData.unit} available)
              </span>
            ) : (
              <span className="text-red-600 font-medium">Out of Stock</span>
            )}
          </div>

          {/* Group Buying Alert */}
          {productData.active_group && (
            <Alert className="border-green-600 bg-green-50">
              <Users className="h-4 w-4 text-green-600" />
              <AlertTitle className="text-green-700">Group Buy Active!</AlertTitle>
              <AlertDescription className="space-y-2">
                <p className="text-green-600">
                  Save {productData.active_group.discount_percent}% when joining this group buy
                </p>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span>Progress:</span>
                    <span className="font-medium">
                      {productData.active_group.current_quantity}/{productData.active_group.target_quantity}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-green-600 h-2 rounded-full transition-all"
                      style={{ width: `${productData.active_group.progress_percent}%` }}
                    />
                  </div>
                </div>
                <Button variant="default" className="w-full mt-2" asChild>
                  <Link to={`/buying-groups/${productData.active_group.id}`}>
                    <Users className="mr-2 h-4 w-4" />
                    Join Group Buy
                  </Link>
                </Button>
              </AlertDescription>
            </Alert>
          )}

          {/* Actions */}
          <div className="space-y-3">
            <Button 
              size="lg" 
              className="w-full"
              disabled={!productData.in_stock}
              onClick={handleAddToCart}
            >
              <ShoppingCart className="mr-2 h-5 w-5" />
              Add to Cart
            </Button>
            
            <p className="text-xs text-center text-muted-foreground">
              Vendor minimum order: £{productData.vendor.min_order_value}
            </p>
            
            {productData.active_group && (
              <p className="text-xs text-center text-muted-foreground">
                💡 Or join the group buy above for {productData.active_group.discount_percent}% discount
              </p>
            )}
          </div>

          {/* Vendor Info Card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Vendor Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">FSA Rating:</span>
                <div className="flex items-center gap-1">
                  {productData.vendor.fsa_rating_value ? (
                    <>
                      <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                      <span className="font-medium">
                        {productData.vendor.fsa_rating_display}
                      </span>
                    </>
                  ) : (
                    <span className="text-sm">Not rated</span>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Delivery Radius:</span>
                <div className="flex items-center gap-1">
                  <MapPin className="h-4 w-4" />
                  <span className="font-medium">
                    {productData.vendor.delivery_radius_km}km
                  </span>
                </div>
              </div>
              <Button variant="outline" className="w-full" asChild>
                <Link to={`/vendors/${productData.vendor.id}`}>
                  View All Products from {productData.vendor.business_name}
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Description Section */}
      <Card>
        <CardHeader>
          <CardTitle>Product Description</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground leading-relaxed">
            {productData.description}
          </p>
        </CardContent>
      </Card>

      {/* Allergen Information */}
      {productData.contains_allergens && (
        <Card className="border-amber-600">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-700">
              <AlertTriangle className="h-5 w-5" />
              Allergen Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {productData.allergen_statement && (
              <Alert variant="destructive">
                <AlertDescription>{productData.allergen_statement}</AlertDescription>
              </Alert>
            )}
            
            <div>
              <p className="font-medium mb-2">Contains:</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(productData.allergen_info)
                  .filter(([_, value]) => value === true)
                  .map(([allergen]) => (
                    <Badge key={allergen} variant="destructive">
                      {allergen.replace(/_/g, ' ').toUpperCase()}
                    </Badge>
                  ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Product Details */}
      <Card>
        <CardHeader>
          <CardTitle>Product Details</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            <div>
              <dt className="text-sm text-muted-foreground">SKU</dt>
              <dd className="font-medium">{productData.sku}</dd>
            </div>
            {productData.barcode && (
              <div>
                <dt className="text-sm text-muted-foreground">Barcode</dt>
                <dd className="font-medium">{productData.barcode}</dd>
              </div>
            )}
            <div>
              <dt className="text-sm text-muted-foreground">Unit</dt>
              <dd className="font-medium">{productData.unit}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Category</dt>
              <dd className="font-medium">
                {productData.category?.name || 'Uncategorized'}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}

function ProductDetailSkeleton() {
  return (
    <div className="container mx-auto py-8 space-y-8">
      <Skeleton className="h-10 w-32" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-4">
          <Skeleton className="aspect-square w-full" />
          <div className="grid grid-cols-4 gap-2">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="aspect-square" />
            ))}
          </div>
        </div>
        <div className="space-y-6">
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-6 w-1/2" />
          <Skeleton className="h-16 w-1/3" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    </div>
  );
}