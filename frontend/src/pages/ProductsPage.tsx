import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { productsApi } from '@/api/endpoints';
import { ProductCard } from '@/components/shared/ProductCard';
import { ProductFilters, ProductFiltersState } from '@/components/products/ProductFilters';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent } from '@/components/ui/card';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import { Search, Filter, X } from 'lucide-react';

export function ProductsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [page, setPage] = useState(1);
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

  // Initialize filters from URL params
  const [filters, setFilters] = useState<ProductFiltersState>({
    categories: searchParams.get('categories')?.split(',').map(Number).filter(Boolean) || [],
    tags: searchParams.get('tags')?.split(',').map(Number).filter(Boolean) || [],
    minPrice: Number(searchParams.get('minPrice')) || 0,
    maxPrice: Number(searchParams.get('maxPrice')) || 100,
    inStockOnly: searchParams.get('inStock') === 'true',
    allergenFree: searchParams.get('allergenFree')?.split(',').filter(Boolean) || [],
    minFsaRating: searchParams.get('minFsa') ? Number(searchParams.get('minFsa')) : undefined,
  });

  // Build API params from filters
  const apiParams = useMemo(() => {
    const params: any = {
      page,
      page_size: 12,
    };

    if (searchQuery) params.search = searchQuery;
    if (filters.categories.length > 0) params.category = filters.categories[0]; // Backend supports single category
    if (filters.minPrice > 0) params.min_price = filters.minPrice;
    if (filters.maxPrice < 100) params.max_price = filters.maxPrice;
    if (filters.inStockOnly) params.in_stock_only = true;
    if (filters.minFsaRating) params.min_fsa_rating = filters.minFsaRating;

    return params;
  }, [page, searchQuery, filters]);

  const { data, isLoading, error } = useQuery({
    queryKey: ['products', apiParams],
    queryFn: () => productsApi.list(apiParams),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    updateUrlParams();
  };

  const handleFiltersChange = (newFilters: ProductFiltersState) => {
    setFilters(newFilters);
    setPage(1);
    updateUrlParams(newFilters);
  };

  const updateUrlParams = (filtersToUse = filters) => {
    const params = new URLSearchParams();
    
    if (searchQuery) params.set('search', searchQuery);
    if (filtersToUse.categories.length > 0) params.set('categories', filtersToUse.categories.join(','));
    if (filtersToUse.tags.length > 0) params.set('tags', filtersToUse.tags.join(','));
    if (filtersToUse.minPrice > 0) params.set('minPrice', filtersToUse.minPrice.toString());
    if (filtersToUse.maxPrice < 100) params.set('maxPrice', filtersToUse.maxPrice.toString());
    if (filtersToUse.inStockOnly) params.set('inStock', 'true');
    if (filtersToUse.allergenFree.length > 0) params.set('allergenFree', filtersToUse.allergenFree.join(','));
    if (filtersToUse.minFsaRating) params.set('minFsa', filtersToUse.minFsaRating.toString());

    setSearchParams(params);
  };

  const activeFiltersCount = 
    filters.categories.length +
    filters.tags.length +
    filters.allergenFree.length +
    (filters.inStockOnly ? 1 : 0) +
    (filters.minFsaRating ? 1 : 0) +
    ((filters.minPrice > 0 || filters.maxPrice < 100) ? 1 : 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Products</h1>
          <p className="text-muted-foreground">
            Browse products from verified UK suppliers
          </p>
        </div>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search products..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
          {searchQuery && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="absolute right-2 top-1/2 transform -translate-y-1/2"
              onClick={() => {
                setSearchQuery('');
                setPage(1);
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
        <Button type="submit">Search</Button>
        
        {/* Mobile Filters Button */}
        <Sheet open={mobileFiltersOpen} onOpenChange={setMobileFiltersOpen}>
          <SheetTrigger asChild>
            <Button variant="outline" className="lg:hidden">
              <Filter className="mr-2 h-4 w-4" />
              Filters
              {activeFiltersCount > 0 && (
                <span className="ml-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
                  {activeFiltersCount}
                </span>
              )}
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-80 overflow-y-auto">
            <ProductFilters 
              filters={filters} 
              onChange={handleFiltersChange}
              onClose={() => setMobileFiltersOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </form>

      {/* Results Count */}
      {data && (
        <div className="text-sm text-muted-foreground">
          {data.data.count} products found
          {activeFiltersCount > 0 && ` • ${activeFiltersCount} filter${activeFiltersCount !== 1 ? 's' : ''} applied`}
        </div>
      )}

      {/* Error State */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load products. Please try again later.
          </AlertDescription>
        </Alert>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Desktop Filters Sidebar */}
        <aside className="hidden lg:block">
          <ProductFilters filters={filters} onChange={handleFiltersChange} />
        </aside>

        {/* Products Grid */}
        <div className="lg:col-span-3 space-y-6">
          {/* Loading State */}
          {isLoading && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {[...Array(6)].map((_, i) => (
                <Card key={i}>
                  <Skeleton className="aspect-square" />
                  <CardContent className="pt-4 space-y-2">
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-8 w-1/3" />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Products Grid */}
          {data && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {data.data.results.map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>

              {/* Pagination */}
              {data.data.count > 12 && (
                <div className="flex justify-center gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={!data.data.previous || isLoading}
                  >
                    Previous
                  </Button>
                  <div className="flex items-center px-4">
                    Page {page}
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => setPage(p => p + 1)}
                    disabled={!data.data.next || isLoading}
                  >
                    Next
                  </Button>
                </div>
              )}
            </>
          )}

          {/* Empty State */}
          {data && data.data.results.length === 0 && (
            <div className="text-center py-12">
              <p className="text-muted-foreground">No products found</p>
              {(searchQuery || activeFiltersCount > 0) && (
                <Button
                  variant="link"
                  onClick={() => {
                    setSearchQuery('');
                    setFilters({
                      categories: [],
                      tags: [],
                      minPrice: 0,
                      maxPrice: 100,
                      inStockOnly: false,
                      allergenFree: [],
                      minFsaRating: undefined,
                    });
                    setPage(1);
                  }}
                >
                  Clear all filters
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}