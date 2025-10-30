// frontend/src/components/vendors/FSARatingBadge.tsx
// Food Standards Agency rating badge

import { cn } from '@/lib/utils';
import { Star } from 'lucide-react';

interface FSARatingBadgeProps {
  rating: number;
  size?: 'small' | 'medium' | 'large';
  className?: string;
}

export function FSARatingBadge({
  rating,
  size = 'medium',
  className,
}: FSARatingBadgeProps) {
  const sizeClasses = {
    small: 'text-xs py-1 px-2',
    medium: 'text-sm py-2 px-3',
    large: 'text-lg py-3 px-4',
  };

  const starSizeClasses = {
    small: 'h-3 w-3',
    medium: 'h-4 w-4',
    large: 'h-6 w-6',
  };

  const getRatingColor = (rating: number) => {
    if (rating === 5) return 'bg-green-100 text-green-800 border-green-300';
    if (rating === 4) return 'bg-blue-100 text-blue-800 border-blue-300';
    if (rating === 3) return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    if (rating <= 2) return 'bg-orange-100 text-orange-800 border-orange-300';
    return 'bg-gray-100 text-gray-800 border-gray-300';
  };

  return (
    <div
      className={cn(
        'inline-flex items-center gap-2 rounded-lg border-2 font-semibold',
        sizeClasses[size],
        getRatingColor(rating),
        className
      )}
    >
      <span>FSA Rating</span>
      <div className="flex items-center gap-1">
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            className={cn(
              starSizeClasses[size],
              i < rating ? 'fill-current' : 'fill-none'
            )}
          />
        ))}
      </div>
      <span className="font-bold">{rating}/5</span>
    </div>
  );
}