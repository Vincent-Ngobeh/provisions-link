// frontend/src/components/buying-groups/CountdownTimer.tsx
// Countdown interval restarts when WebSocket updates arrive

import { useEffect, useState, useRef } from 'react';
import { Clock, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface CountdownTimerProps {
  expiresAt: string;
  timeRemainingSeconds?: number; // From WebSocket
  showBadge?: boolean;
  onExpired?: () => void;
}

export function CountdownTimer({
  expiresAt,
  timeRemainingSeconds,
  showBadge = true,
  onExpired,
}: CountdownTimerProps) {
  const [timeLeft, setTimeLeft] = useState<number>(0);
  const [isExpired, setIsExpired] = useState(false);
  
  // Use ref to track the callback to avoid adding it to dependencies
  const onExpiredRef = useRef(onExpired);
  
  // Use ref to track the interval so we can clear it manually
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // Update ref when callback changes
  useEffect(() => {
    onExpiredRef.current = onExpired;
  }, [onExpired]);

  // EFFECT 1: Sync timeLeft state with props (WebSocket updates or initial load)
  // This effect runs whenever timeRemainingSeconds or expiresAt changes
  useEffect(() => {
    let newTimeLeft: number;
    
    if (timeRemainingSeconds !== undefined) {
      // Use WebSocket time if available (most accurate)
      newTimeLeft = timeRemainingSeconds;
    } else {
      // Calculate from expiresAt timestamp
      const expiryTime = new Date(expiresAt).getTime();
      const now = Date.now();
      newTimeLeft = Math.max(0, Math.floor((expiryTime - now) / 1000));
    }
    
    setTimeLeft(newTimeLeft);
    setIsExpired(newTimeLeft <= 0);
  }, [expiresAt, timeRemainingSeconds]);

  // EFFECT 2: Countdown interval that RESTARTS when timeLeft changes
  // This effect now depends on timeLeft, so it restarts the interval
  // whenever WebSocket updates arrive
  useEffect(() => {
    // Clear any existing interval to prevent multiple intervals running
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    // Don't start interval if already expired
    if (timeLeft <= 0) {
      return;
    }

    // Start new countdown interval from current timeLeft value
    intervalRef.current = setInterval(() => {
      setTimeLeft((prevTime) => {
        const newTime = Math.max(0, prevTime - 1);
        
        // Check if just expired
        if (newTime === 0 && prevTime > 0) {
          setIsExpired(true);
          // Call onExpired callback via ref (doesn't cause re-render)
          onExpiredRef.current?.();
        }
        
        return newTime;
      });
    }, 1000);

    // Cleanup: Clear interval when component unmounts or timeLeft changes
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [timeLeft]); // Restart interval when timeLeft updates from WebSocket

  // Format time remaining
  const formatTime = (seconds: number): string => {
    if (seconds <= 0) return 'Expired';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (days > 0) {
      return `${days}d ${hours}h`;
    }
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  };

  const timeString = formatTime(timeLeft);
  const isUrgent = timeLeft > 0 && timeLeft < 3600; // Less than 1 hour
  const isCritical = timeLeft > 0 && timeLeft < 600; // Less than 10 minutes

  if (isExpired) {
    return (
      <div className="flex items-center gap-2 text-red-600">
        <AlertCircle className="h-4 w-4" />
        <span className="text-sm font-medium">Expired</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Clock 
        className={`h-4 w-4 ${
          isCritical ? 'text-red-600 animate-pulse' : 
          isUrgent ? 'text-orange-600' : 
          'text-muted-foreground'
        }`} 
      />
      
      {showBadge ? (
        <Badge 
          variant={isCritical ? 'destructive' : isUrgent ? 'outline' : 'secondary'}
          className={
            isCritical ? 'animate-pulse' : 
            isUrgent ? 'border-orange-500 text-orange-700' : 
            ''
          }
        >
          {timeString}
        </Badge>
      ) : (
        <span 
          className={`text-sm font-medium ${
            isCritical ? 'text-red-600' : 
            isUrgent ? 'text-orange-600' : 
            'text-muted-foreground'
          }`}
        >
          {timeString}
        </span>
      )}

      {isUrgent && (
        <span className="text-xs text-orange-600 font-medium">
          {isCritical ? '⚠️ Ending soon!' : '⏰ Limited time'}
        </span>
      )}
    </div>
  );
}