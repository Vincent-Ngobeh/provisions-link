// frontend/src/components/buying-groups/ParticipantsList.tsx

import { useEffect, useState, useRef } from 'react';
import { Users, TrendingUp, UserPlus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

interface ParticipantsListProps {
  participantsCount: number;
  showAnimation?: boolean;
  showTrend?: boolean;
  variant?: 'inline' | 'card';
}

export function ParticipantsList({
  participantsCount,
  showAnimation = true,
  showTrend = false,
  variant = 'inline',
}: ParticipantsListProps) {
  const [displayCount, setDisplayCount] = useState(participantsCount);
  const [isIncreasing, setIsIncreasing] = useState(false);
  const [previousCount, setPreviousCount] = useState(participantsCount);

  // Use ref to avoid recreating interval on every render
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const animationTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // FIXED: Animate count changes without dependencies on displayCount
  useEffect(() => {
    // Clear any existing intervals/timeouts
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (animationTimeoutRef.current) {
      clearTimeout(animationTimeoutRef.current);
      animationTimeoutRef.current = null;
    }

    // If animation disabled or count unchanged, just update
    if (!showAnimation || participantsCount === displayCount) {
      setDisplayCount(participantsCount);
      setPreviousCount(participantsCount);
      setIsIncreasing(false);
      return;
    }

    // Determine if count is increasing
    const increasing = participantsCount > displayCount;
    setIsIncreasing(increasing);

    // Animate the number change
    const startCount = displayCount;
    const endCount = participantsCount;
    const duration = 500; // ms
    const steps = 10;
    const stepDuration = duration / steps;
    const increment = (endCount - startCount) / steps;

    let currentStep = 0;

    intervalRef.current = setInterval(() => {
      currentStep++;

      if (currentStep >= steps) {
        setDisplayCount(endCount);
        setPreviousCount(endCount);
        
        // Clear interval
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }

        // Reset animation state after delay
        animationTimeoutRef.current = setTimeout(() => {
          setIsIncreasing(false);
        }, 1000);
      } else {
        setDisplayCount(Math.round(startCount + increment * currentStep));
      }
    }, stepDuration);

    // Cleanup function
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (animationTimeoutRef.current) {
        clearTimeout(animationTimeoutRef.current);
        animationTimeoutRef.current = null;
      }
    };
  }, [participantsCount, showAnimation]); // Only depend on participantsCount and showAnimation

  const countChange = displayCount - previousCount;

  if (variant === 'card') {
    return (
      <Card className={`transition-all duration-300 ${isIncreasing ? 'ring-2 ring-green-500' : ''}`}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className={`
                p-2 rounded-full transition-colors duration-300
                ${isIncreasing ? 'bg-green-100' : 'bg-muted'}
              `}>
                <Users className={`h-5 w-5 ${
                  isIncreasing ? 'text-green-600' : 'text-muted-foreground'
                }`} />
              </div>
              
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold">{displayCount}</span>
                  {isIncreasing && (
                    <UserPlus className="h-5 w-5 text-green-600 animate-bounce" />
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  {displayCount === 1 ? 'Participant' : 'Participants'}
                </p>
              </div>
            </div>

            {showTrend && countChange > 0 && (
              <Badge className="bg-green-600 text-white hover:bg-green-700">
                <TrendingUp className="h-3 w-3 mr-1" />
                +{countChange}
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Inline variant
  return (
    <div className={`
      inline-flex items-center gap-2 px-3 py-1.5 rounded-md transition-all duration-300
      ${isIncreasing ? 'bg-green-50 ring-1 ring-green-200' : 'bg-muted'}
    `}>
      <Users className={`h-4 w-4 ${
        isIncreasing ? 'text-green-600' : 'text-muted-foreground'
      }`} />
      
      <span className={`font-medium ${
        isIncreasing ? 'text-green-700' : 'text-foreground'
      }`}>
        {displayCount}
      </span>
      
      <span className="text-sm text-muted-foreground">
        {displayCount === 1 ? 'participant' : 'participants'}
      </span>

      {isIncreasing && (
        <UserPlus className="h-4 w-4 text-green-600 animate-bounce ml-1" />
      )}

      {showTrend && countChange > 0 && (
        <Badge 
          variant="outline" 
          className="ml-2 border-green-500 text-green-700 text-xs"
        >
          +{countChange}
        </Badge>
      )}
    </div>
  );
}