import { useQuery } from '@tanstack/react-query';
import { categoriesApi } from '@/api/endpoints';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Slider } from '@/components/ui/slider';
import { Separator } from '@/components/ui/separator';
import { X } from 'lucide-react';

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

// Map display names to backend field names
const ALLERGENS = [
  { value: 'cereals_containing_gluten', label: 'Gluten' },
  { value: 'milk', label: 'Dairy' },
  { value: 'eggs', label: 'Eggs' },
  { value: 'tree_nuts', label: 'Tree Nuts' },
  { value: 'peanuts', label: 'Peanuts' },
  { value: 'fish', label: 'Fish' },
  { value: 'crustaceans', label: 'Shellfish (Crustaceans)' },
  { value: 'soybeans', label: 'Soy' },
  { value: 'sesame', label: 'Sesame' },
  { value: 'molluscs', label: 'Molluscs' },
];

const FSA_RATINGS = [
  { value: 5, label: '5 - Very Good' },
  { value: 4, label: '4 - Good' },
  { value: 3, label: '3 - Generally Satisfactory' },
];

export function ProductFilters({ filters, onChange, onClose }: ProductFiltersProps) {
  // Fetch categories from API
  const { data: categoriesData } = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoriesApi.list(),
  });

  // Extract categories from paginated response
  const categories = categoriesData?.data?.results || [];

  console.log('Categories data:', categoriesData);
  console.log('Categories array:', categories);

  const handleCategoryToggle = (categoryId: number) => {
    // Single-select: toggle on/off
    const newCategories = filters.categories.includes(categoryId)
      ? [] // Deselect if already selected
      : [categoryId]; // Select only this category
    
    onChange({ ...filters, categories: newCategories });
  };

  const handleAllergenToggle = (allergenValue: string) => {
    const newAllergens = filters.allergenFree.includes(allergenValue)
      ? filters.allergenFree.filter(a => a !== allergenValue)
      : [...filters.allergenFree, allergenValue];
    
    onChange({ ...filters, allergenFree: newAllergens });
  };

  const handlePriceChange = (values: number[]) => {
    // Update filters directly without intermediate state
    onChange({ 
      ...filters, 
      minPrice: values[0], 
      maxPrice: values[1] 
    });
  };

  const handleFsaRatingChange = (rating: number) => {
    onChange({ 
      ...filters, 
      minFsaRating: filters.minFsaRating === rating ? undefined : rating 
    });
  };

  const handleClearAll = () => {
    onChange({
      categories: [],
      tags: [],
      minPrice: 0,
      maxPrice: 50,
      inStockOnly: false,
      allergenFree: [],
      minFsaRating: undefined,
    });
  };

  const activeFiltersCount = 
    filters.categories.length +
    filters.tags.length +
    filters.allergenFree.length +
    (filters.inStockOnly ? 1 : 0) +
    (filters.minFsaRating ? 1 : 0) +
    ((filters.minPrice > 0 || filters.maxPrice < 50) ? 1 : 0);

  return (
    <Card className="h-fit text-sm">
      <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
        <CardTitle className="text-base">Filters</CardTitle>
        <div className="flex items-center gap-2">
          {activeFiltersCount > 0 && (
            <Badge variant="secondary" className="text-xs">{activeFiltersCount}</Badge>
          )}
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 px-4 pb-4">
        {/* Clear All Button */}
        {activeFiltersCount > 0 && (
          <>
            <Button 
              variant="outline" 
              size="sm" 
              onClick={handleClearAll}
              className="w-full"
            >
              Clear All Filters
            </Button>
            <Separator />
          </>
        )}

        {/* Categories */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Categories</Label>
          <div className="space-y-1.5">
            {categories.length === 0 ? (
              <p className="text-xs text-muted-foreground">Loading categories...</p>
            ) : (
              categories.map((category: any) => (
                <div key={category.id} className="flex items-center space-x-2">
                  <Checkbox
                    id={`category-${category.id}`}
                    checked={filters.categories.includes(category.id)}
                    onCheckedChange={() => handleCategoryToggle(category.id)}
                  />
                  <label
                    htmlFor={`category-${category.id}`}
                    className="text-xs font-normal leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                  >
                    {category.name}
                  </label>
                </div>
              ))
            )}
          </div>
        </div>

        <Separator />

        {/* Price Range */}
        <div className="space-y-3">
          <Label className="text-sm font-medium">Price Range</Label>
          <div className="pt-2 pb-1">
            <Slider
              value={[filters.minPrice, filters.maxPrice]}
              min={0}
              max={50}
              step={1}
              onValueChange={handlePriceChange}
              className="w-full"
            />
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>£{filters.minPrice}</span>
            <span>£{filters.maxPrice}</span>
          </div>
        </div>

        <Separator />

        {/* Stock Status */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Availability</Label>
          <div className="flex items-center space-x-2">
            <Checkbox
              id="in-stock"
              checked={filters.inStockOnly}
              onCheckedChange={(checked) => 
                onChange({ ...filters, inStockOnly: checked as boolean })
              }
            />
            <label
              htmlFor="in-stock"
              className="text-xs font-normal leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
            >
              In stock only
            </label>
          </div>
        </div>

        <Separator />

        {/* FSA Rating */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Minimum FSA Rating</Label>
          <div className="space-y-1.5">
            {FSA_RATINGS.map((rating) => (
              <div key={rating.value} className="flex items-center space-x-2">
                <Checkbox
                  id={`fsa-${rating.value}`}
                  checked={filters.minFsaRating === rating.value}
                  onCheckedChange={() => handleFsaRatingChange(rating.value)}
                />
                <label
                  htmlFor={`fsa-${rating.value}`}
                  className="text-xs font-normal leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                >
                  {rating.label}
                </label>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Allergen Free */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Allergen Free</Label>
          <div className="space-y-1.5">
            {ALLERGENS.map((allergen) => (
              <div key={allergen.value} className="flex items-center space-x-2">
                <Checkbox
                  id={`allergen-${allergen.value}`}
                  checked={filters.allergenFree.includes(allergen.value)}
                  onCheckedChange={() => handleAllergenToggle(allergen.value)}
                />
                <label
                  htmlFor={`allergen-${allergen.value}`}
                  className="text-xs font-normal leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                >
                  {allergen.label}
                </label>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}