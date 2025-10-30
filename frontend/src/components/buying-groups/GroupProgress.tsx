import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Users, Target } from 'lucide-react';
import { cn } from '@/lib/utils';

interface GroupProgressProps {
  currentQuantity: number;
  targetQuantity: number;
  minQuantity: number;
  progressPercent: number;
  participantsCount?: number;
  animate?: boolean;
}

export function GroupProgress({
  currentQuantity,
  targetQuantity,
  minQuantity,
  progressPercent,
  participantsCount,
  animate = false,
}: GroupProgressProps) {
  const [displayProgress, setDisplayProgress] = useState(0);

  useEffect(() => {
    if (animate) {
      // Animate from 0 to actual progress
      const timer = setTimeout(() => {
        setDisplayProgress(progressPercent);
      }, 100);
      return () => clearTimeout(timer);
    } else {
      setDisplayProgress(progressPercent);
    }
  }, [progressPercent, animate]);

  const minPercentage = (minQuantity / targetQuantity) * 100;
  const isAboveMin = currentQuantity >= minQuantity;
  const isTargetReached = currentQuantity >= targetQuantity;

  const getProgressColor = () => {
    if (isTargetReached) return 'bg-green-500';
    if (isAboveMin) return 'bg-blue-500';
    return 'bg-gray-400';
  };

  return (
    <div className="space-y-3">
      <div className="relative">
        <div className="relative h-3 w-full overflow-hidden rounded-full bg-secondary">
          <div
            className={cn(
              'h-full transition-all duration-500 ease-out',
              getProgressColor()
            )}
            style={{ width: `${Math.min(displayProgress, 100)}%` }}
          />
        </div>
        
        {/* Minimum threshold indicator */}
        {minPercentage < 100 && (
          <div
            className="absolute top-0 h-3 w-0.5 bg-yellow-500"
            style={{ left: `${minPercentage}%` }}
            title={`Minimum: ${minQuantity} units`}
          />
        )}
      </div>

      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <Target className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{currentQuantity || 0}</span>
            <span className="text-muted-foreground">/ {targetQuantity}</span>
          </div>
          
          {participantsCount !== undefined && (
            <div className="flex items-center gap-1.5">
              <Users className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">{participantsCount || 0}</span>
              <span className="text-muted-foreground">participants</span>
            </div>
          )}
        </div>

        <Badge 
          variant={
            isTargetReached 
              ? 'default' 
              : isAboveMin 
              ? 'secondary' 
              : 'outline'
          }
          className={cn(
            isTargetReached && 'bg-green-100 text-green-800 hover:bg-green-100',
            isAboveMin && !isTargetReached && 'bg-blue-100 text-blue-800 hover:bg-blue-100'
          )}
        >
          {Math.min(displayProgress, 100).toFixed(1)}%
        </Badge>
      </div>

      <p className="text-xs text-muted-foreground">
        {isTargetReached ? (
          <span className="text-green-600 font-medium">
            Target reached! Discount unlocked for all participants.
          </span>
        ) : isAboveMin ? (
          <span className="text-blue-600 font-medium">
            Minimum reached! Group will proceed even if target is not met.
          </span>
        ) : (
          <span>
            Need {Math.max(0, minQuantity - currentQuantity)} more units to reach minimum ({minPercentage.toFixed(0)}%)
          </span>
        )}
      </p>
    </div>
  );
}