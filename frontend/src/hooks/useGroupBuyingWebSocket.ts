// frontend/src/hooks/useGroupBuyingWebSocket.ts
// React hook for managing WebSocket connection to group buying updates

import { useEffect, useState, useCallback, useRef } from 'react';
import { groupBuyingWS, ConnectionState } from '@/lib/websocket';

export interface GroupProgressData {
  group_id: number;
  current_quantity: number;
  target_quantity: number;
  progress_percent: number;
  participants_count: number;
  time_remaining_seconds?: number;
}

export interface ThresholdReachedData {
  group_id: number;
  threshold_percent: number;
  current_quantity: number;
  target_quantity: number;
  message: string;
}

export interface StatusChangeData {
  group_id: number;
  old_status: string;
  new_status: string;
  message: string;
  reason?: string;
}

export interface NewCommitmentData {
  group_id: number;
  buyer_name: string;
  quantity: number;
  new_total: number;
  participants_count: number;
  message: string;
}

export interface CommitmentCancelledData {
  group_id: number;
  quantity: number;
  new_total: number;
  participants_count: number;
  message: string;
}

export interface UseGroupBuyingWebSocketOptions {
  groupId: number | null;
  autoConnect?: boolean;
  onProgressUpdate?: (data: GroupProgressData) => void;
  onThresholdReached?: (data: ThresholdReachedData) => void;
  onStatusChange?: (data: StatusChangeData) => void;
  onNewCommitment?: (data: NewCommitmentData) => void;
  onCommitmentCancelled?: (data: CommitmentCancelledData) => void;
}

export function useGroupBuyingWebSocket({
  groupId,
  autoConnect = true,
  onProgressUpdate,
  onThresholdReached,
  onStatusChange,
  onNewCommitment,
  onCommitmentCancelled,
}: UseGroupBuyingWebSocketOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    groupBuyingWS.getState()
  );
  const [lastUpdate, setLastUpdate] = useState<any>(null);
  const [progressData, setProgressData] = useState<GroupProgressData | null>(null);

  // Use refs for callbacks to avoid re-subscribing on every render
  const progressRef = useRef(onProgressUpdate);
  const thresholdRef = useRef(onThresholdReached);
  const statusRef = useRef(onStatusChange);
  const commitmentRef = useRef(onNewCommitment);
  const cancelledRef = useRef(onCommitmentCancelled);

  // Update refs when callbacks change
  useEffect(() => {
    progressRef.current = onProgressUpdate;
    thresholdRef.current = onThresholdReached;
    statusRef.current = onStatusChange;
    commitmentRef.current = onNewCommitment;
    cancelledRef.current = onCommitmentCancelled;
  }, [onProgressUpdate, onThresholdReached, onStatusChange, onNewCommitment, onCommitmentCancelled]);

  // Connect to WebSocket
  useEffect(() => {
    if (!autoConnect) return;

    groupBuyingWS.connect();

    // Subscribe to connection state changes
    const unsubscribe = groupBuyingWS.onStateChange((state) => {
      setConnectionState(state);
    });

    return () => {
      unsubscribe();
    };
  }, [autoConnect]);

  // Subscribe to group when groupId changes
  useEffect(() => {
    if (!groupId || connectionState !== 'connected') return;

    console.log(`[Hook] Subscribing to group ${groupId}`);
    groupBuyingWS.subscribeToGroup(groupId);

    return () => {
      console.log(`[Hook] Unsubscribing from group ${groupId}`);
      groupBuyingWS.unsubscribeFromGroup();
    };
  }, [groupId, connectionState]);

  // Setup event handlers
  useEffect(() => {
    // Connection established
    const handleConnectionEstablished = (data: any) => {
      console.log('[Hook] Connection established:', data);
    };

    // Subscribed to group
    const handleSubscribed = (data: any) => {
      console.log('[Hook] Subscribed to group:', data);
      if (data.current_state) {
        setProgressData(data.current_state);
      }
    };

    // Progress update
    const handleProgressUpdate = (data: GroupProgressData) => {
      console.log('[Hook] Progress update:', data);
      setProgressData(data);
      setLastUpdate({ type: 'progress', data, timestamp: Date.now() });
      progressRef.current?.(data);
    };

    // Threshold reached
    const handleThresholdReached = (data: ThresholdReachedData) => {
      console.log('[Hook] Threshold reached:', data);
      setLastUpdate({ type: 'threshold', data, timestamp: Date.now() });
      thresholdRef.current?.(data);
    };

    // Status change
    const handleStatusChange = (data: StatusChangeData) => {
      console.log('[Hook] Status change:', data);
      setLastUpdate({ type: 'status_change', data, timestamp: Date.now() });
      statusRef.current?.(data);
    };

    // New commitment
    const handleNewCommitment = (data: NewCommitmentData) => {
      console.log('[Hook] New commitment:', data);
      setLastUpdate({ type: 'new_commitment', data, timestamp: Date.now() });
      commitmentRef.current?.(data);
    };

    // Commitment cancelled
    const handleCommitmentCancelled = (data: CommitmentCancelledData) => {
      console.log('[Hook] Commitment cancelled:', data);
      setLastUpdate({ type: 'commitment_cancelled', data, timestamp: Date.now() });
      cancelledRef.current?.(data);
    };

    // Error handling
    const handleError = (data: any) => {
      console.error('[Hook] WebSocket error:', data);
    };

    // Register all handlers
    groupBuyingWS.on('connection_established', handleConnectionEstablished);
    groupBuyingWS.on('subscribed', handleSubscribed);
    groupBuyingWS.on('progress_update', handleProgressUpdate);
    groupBuyingWS.on('threshold_reached', handleThresholdReached);
    groupBuyingWS.on('status_change', handleStatusChange);
    groupBuyingWS.on('new_commitment', handleNewCommitment);
    groupBuyingWS.on('commitment_cancelled', handleCommitmentCancelled);
    groupBuyingWS.on('error', handleError);

    // Cleanup
    return () => {
      groupBuyingWS.off('connection_established', handleConnectionEstablished);
      groupBuyingWS.off('subscribed', handleSubscribed);
      groupBuyingWS.off('progress_update', handleProgressUpdate);
      groupBuyingWS.off('threshold_reached', handleThresholdReached);
      groupBuyingWS.off('status_change', handleStatusChange);
      groupBuyingWS.off('new_commitment', handleNewCommitment);
      groupBuyingWS.off('commitment_cancelled', handleCommitmentCancelled);
      groupBuyingWS.off('error', handleError);
    };
  }, []);

  // Manual control methods
  const connect = useCallback(() => {
    groupBuyingWS.connect();
  }, []);

  const disconnect = useCallback(() => {
    groupBuyingWS.disconnect();
  }, []);

  return {
    connectionState,
    isConnected: connectionState === 'connected',
    isConnecting: connectionState === 'connecting',
    isReconnecting: connectionState === 'reconnecting',
    isDisconnected: connectionState === 'disconnected',
    hasError: connectionState === 'error',
    progressData,
    lastUpdate,
    connect,
    disconnect,
  };
}