import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { categoriesApi, tagsApi } from '@/api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { X, Loader2 } from 'lucide-react';

export interface ProductFiltersState {
  categories: number[];
  tags: number[];
  minPrice: number;
  maxPrice: number;
  inStockOnly: boolean;
  allergenFree: string[];
  minFsaRating?: number;
}

interface ProductFiltersProps {
  filters: ProductFiltersState;
  onChange: (filters: ProductFiltersState) => void;
  onClose?: () => void;
}

const ALLERGENS = [
  'celery',
  'cereals_containing_gluten',
  'crustaceans',
  'eggs',
  'fish',
  'lupin',
  'milk',
  'molluscs',
  'mustard',
  'tree_nuts',
  'peanuts',
  'sesame',
  'soybeans',
  'sulphur_dioxide',
];

// FIX 9: Reduced price range to £0-£50 (from £200)
const PRICE_MIN = 0;
const PRICE_MAX = 50;

export function ProductFilters({ filters, onChange, onClose }: ProductFiltersProps) {
  const [localFilters, setLocalFilters] = useState(filters);
  
  // Use ref to avoid onChange in dependencies
  const onChangeRef = useRef(onChange);

  // Update ref when callback changes
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Sync localFilters with parent filters prop
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  // FIXED: Debounced notification to parent
  // This prevents infinite loops when price slider is moved rapidly
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      onChangeRef.current(localFilters);
    }, 300); // 300ms debounce

    return () => clearTimeout(timeoutId);
  }, [localFilters]);

  // Fetch categories
  const { data: categoriesData, isLoading: categoriesLoading } = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoriesApi.list(),
  });

  // Fetch tags
  const { data: tagsData, isLoading: tagsLoading } = useQuery({
    queryKey: ['tags'],
    queryFn: () => tagsApi.list(),
  });

  const handleCategoryToggle = (categoryId: number) => {
    setLocalFilters(prev => ({
      ...prev,
      categories: prev.categories.includes(categoryId)
        ? prev.categories.filter(id => id !== categoryId)
        : [...prev.categories, categoryId],
    }));
  };

  const handleTagToggle = (tagId: number) => {
    setLocalFilters(prev => ({
      ...prev,
      tags: prev.tags.includes(tagId)
        ? prev.tags.filter(id => id !== tagId)
        : [...prev.tags, tagId],
    }));
  };

  const handleAllergenToggle = (allergen: string) => {
    setLocalFilters(prev => ({
      ...prev,
      allergenFree: prev.allergenFree.includes(allergen)
        ? prev.allergenFree.filter(a => a !== allergen)
        : [...prev.allergenFree, allergen],
    }));
  };

  // FIXED: Handle range slider with two values [min, max]
  const handlePriceChange = (values: number[]) => {
    setLocalFilters(prev => ({
      ...prev,
      minPrice: values[0],
      maxPrice: values[1],
    }));
  };

  const clearAllFilters = () => {
    setLocalFilters({
      categories: [],
      tags: [],
      minPrice: PRICE_MIN,
      maxPrice: PRICE_MAX,
      inStockOnly: false,
      allergenFree: [],
      minFsaRating: undefined,
    });
  };

  const activeFiltersCount = 
    localFilters.categories.length +
    localFilters.tags.length +
    localFilters.allergenFree.length +
    (localFilters.inStockOnly ? 1 : 0) +
    (localFilters.minFsaRating ? 1 : 0) +
    ((localFilters.minPrice > PRICE_MIN || localFilters.maxPrice < PRICE_MAX) ? 1 : 0);

  // Safely extract arrays from API responses
  const categories = Array.isArray(categoriesData?.data) 
    ? categoriesData.data 
    : ((categoriesData?.data as any)?.results || []);
  
  const tags = Array.isArray(tagsData?.data) 
    ? tagsData.data 
    : ((tagsData?.data as any)?.results || []);

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-lg">Filters</CardTitle>
        <div className="flex items-center gap-2">
          {activeFiltersCount > 0 && (
            <Badge variant="secondary">{activeFiltersCount} active</Badge>
          )}
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Clear All Button */}
        {activeFiltersCount > 0 && (
          <Button 
            variant="outline" 
            size="sm" 
            onClick={clearAllFilters}
            className="w-full"
          >
            Clear All Filters
          </Button>
        )}

        {/* Categories */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold">Categories</Label>
          {categoriesLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading categories...
            </div>
          ) : categories.length === 0 ? (
            <p className="text-sm text-muted-foreground">No categories available</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {categories.map((category: any) => (
                <div key={category.id} className="flex items-center space-x-2">
                  <Checkbox
                    id={`category-${category.id}`}
                    checked={localFilters.categories.includes(category.id)}
                    onCheckedChange={() => handleCategoryToggle(category.id)}
                  />
                  <Label
                    htmlFor={`category-${category.id}`}
                    className="text-sm font-normal cursor-pointer"
                  >
                    {category.name}
                  </Label>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* FIX 9: Price Range updated to £0-£50 */}
        <div className="space-y-4">
          <Label className="text-sm font-semibold">
            Price Range (per unit)
          </Label>
          <div className="flex items-center justify-between text-sm font-medium">
            <span>£{localFilters.minPrice}</span>
            <span>£{localFilters.maxPrice}</span>
          </div>
          <Slider
            value={[localFilters.minPrice, localFilters.maxPrice]}
            onValueChange={handlePriceChange}
            min={PRICE_MIN}
            max={PRICE_MAX}
            step={5}
            minStepsBetweenThumbs={1}
            className="w-full"
          />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>£{PRICE_MIN}</span>
            <span>£{PRICE_MAX}+</span>
          </div>
        </div>

        <Separator />

        {/* Stock Status */}
        <div className="flex items-center space-x-2">
          <Checkbox
            id="in-stock"
            checked={localFilters.inStockOnly}
            onCheckedChange={(checked) =>
              setLocalFilters(prev => ({ ...prev, inStockOnly: !!checked }))
            }
          />
          <Label htmlFor="in-stock" className="text-sm cursor-pointer">
            In Stock Only
          </Label>
        </div>

        <Separator />

        {/* Tags */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold">Tags</Label>
          {tagsLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading tags...
            </div>
          ) : tags.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tags available</p>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {tags.map((tag: any) => (
                <div key={tag.id} className="flex items-center space-x-2">
                  <Checkbox
                    id={`tag-${tag.id}`}
                    checked={localFilters.tags.includes(tag.id)}
                    onCheckedChange={() => handleTagToggle(tag.id)}
                  />
                  <Label
                    htmlFor={`tag-${tag.id}`}
                    className="text-sm font-normal cursor-pointer"
                  >
                    {tag.name}
                  </Label>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* Allergen Free */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold">Allergen Free</Label>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {ALLERGENS.map((allergen) => (
              <div key={allergen} className="flex items-center space-x-2">
                <Checkbox
                  id={`allergen-${allergen}`}
                  checked={localFilters.allergenFree.includes(allergen)}
                  onCheckedChange={() => handleAllergenToggle(allergen)}
                />
                <Label
                  htmlFor={`allergen-${allergen}`}
                  className="text-sm font-normal cursor-pointer"
                >
                  {allergen.replace(/_/g, ' ')}
                </Label>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* FSA Rating */}
        <div className="space-y-3">
          <Label className="text-sm font-semibold">Minimum FSA Rating</Label>
          <div className="space-y-2">
            {[5, 4, 3].map((rating) => (
              <div key={rating} className="flex items-center space-x-2">
                <Checkbox
                  id={`fsa-${rating}`}
                  checked={localFilters.minFsaRating === rating}
                  onCheckedChange={(checked) =>
                    setLocalFilters(prev => ({
                      ...prev,
                      minFsaRating: checked ? rating : undefined,
                    }))
                  }
                />
                <Label
                  htmlFor={`fsa-${rating}`}
                  className="text-sm font-normal cursor-pointer"
                >
                  {rating}+ Stars
                </Label>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}