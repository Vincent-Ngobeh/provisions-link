// frontend/src/lib/websocket.ts
// WebSocket client for real-time group buying updates

type WebSocketEventHandler = (data: any) => void;

interface WebSocketConfig {
  url: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}

export type ConnectionState = 
  | 'connecting' 
  | 'connected' 
  | 'disconnected' 
  | 'reconnecting' 
  | 'error';

export class GroupBuyingWebSocket {
  private ws: WebSocket | null = null;
  private config: Required<WebSocketConfig>;
  private eventHandlers: Map<string, Set<WebSocketEventHandler>> = new Map();
  private reconnectAttempts = 0;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private connectionState: ConnectionState = 'disconnected';
  private stateChangeHandlers: Set<(state: ConnectionState) => void> = new Set();
  private currentGroupId: number | null = null;

  constructor(config: WebSocketConfig) {
    this.config = {
      url: config.url,
      reconnectInterval: config.reconnectInterval ?? 3000,
      maxReconnectAttempts: config.maxReconnectAttempts ?? 5,
      heartbeatInterval: config.heartbeatInterval ?? 30000,
    };
  }

  /**
   * Connect to WebSocket server
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('[WS] Already connected');
      return;
    }

    this.setConnectionState('connecting');

    // Get JWT token from localStorage
    const token = localStorage.getItem('access_token');
    
    // Include token in WebSocket URL as query param
    const wsUrl = token 
      ? `${this.config.url}?token=${token}`
      : this.config.url;

    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventListeners();
    } catch (error) {
      console.error('[WS] Connection failed:', error);
      this.setConnectionState('error');
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    console.log('[WS] Disconnecting...');
    
    // Clear reconnect timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    // Clear heartbeat
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    // Close WebSocket
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.setConnectionState('disconnected');
    this.reconnectAttempts = 0;
  }

  /**
   * Subscribe to a specific group's updates
   */
  subscribeToGroup(groupId: number): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot subscribe - not connected');
      return;
    }

    console.log(`[WS] Subscribing to group ${groupId}`);
    this.currentGroupId = groupId;

    this.send({
      type: 'subscribe',
      group_id: groupId,
    });
  }

  /**
   * Unsubscribe from current group
   */
  unsubscribeFromGroup(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    if (this.currentGroupId) {
      console.log(`[WS] Unsubscribing from group ${this.currentGroupId}`);
      
      this.send({
        type: 'unsubscribe',
        group_id: this.currentGroupId,
      });

      this.currentGroupId = null;
    }
  }

  /**
   * Add event handler for a specific message type
   */
  on(eventType: string, handler: WebSocketEventHandler): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler);
  }

  /**
   * Remove event handler
   */
  off(eventType: string, handler: WebSocketEventHandler): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  /**
   * Subscribe to connection state changes
   */
  onStateChange(handler: (state: ConnectionState) => void): () => void {
    this.stateChangeHandlers.add(handler);
    
    // Return unsubscribe function
    return () => {
      this.stateChangeHandlers.delete(handler);
    };
  }

  /**
   * Get current connection state
   */
  getState(): ConnectionState {
    return this.connectionState;
  }

  /**
   * Send a message to the server
   */
  private send(data: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot send - not connected');
      return;
    }

    try {
      this.ws.send(JSON.stringify(data));
    } catch (error) {
      console.error('[WS] Send error:', error);
    }
  }

  /**
   * Setup WebSocket event listeners
   */
  private setupEventListeners(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.setConnectionState('connected');
      this.reconnectAttempts = 0;
      this.startHeartbeat();

      // Resubscribe to current group if any
      if (this.currentGroupId) {
        this.subscribeToGroup(this.currentGroupId);
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('[WS] Message received:', message);
        
        this.handleMessage(message);
      } catch (error) {
        console.error('[WS] Failed to parse message:', error);
      }
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      this.setConnectionState('error');
    };

    this.ws.onclose = (event) => {
      console.log('[WS] Disconnected:', event.code, event.reason);
      this.stopHeartbeat();

      if (event.code !== 1000) { // Not a normal closure
        this.setConnectionState('disconnected');
        this.scheduleReconnect();
      } else {
        this.setConnectionState('disconnected');
      }
    };
  }

  /**
   * Handle incoming WebSocket message
   */
  private handleMessage(message: any): void {
    const { type, data } = message;

    // Emit to all handlers for this event type
    const handlers = this.eventHandlers.get(type);
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(data);
        } catch (error) {
          console.error(`[WS] Handler error for ${type}:`, error);
        }
      });
    }

    // Also emit to 'all' handlers
    const allHandlers = this.eventHandlers.get('*');
    if (allHandlers) {
      allHandlers.forEach(handler => {
        try {
          handler(message);
        } catch (error) {
          console.error('[WS] Global handler error:', error);
        }
      });
    }
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.log('[WS] Max reconnect attempts reached');
      this.setConnectionState('error');
      return;
    }

    if (this.reconnectTimeout) {
      return; // Already scheduled
    }

    this.reconnectAttempts++;
    this.setConnectionState('reconnecting');

    const delay = this.config.reconnectInterval * this.reconnectAttempts;
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, delay);
  }

  /**
   * Start heartbeat/ping interval
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'ping' });
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Stop heartbeat interval
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Update connection state and notify listeners
   */
  private setConnectionState(state: ConnectionState): void {
    if (this.connectionState !== state) {
      this.connectionState = state;
      console.log(`[WS] State changed: ${state}`);
      
      this.stateChangeHandlers.forEach(handler => {
        try {
          handler(state);
        } catch (error) {
          console.error('[WS] State change handler error:', error);
        }
      });
    }
  }
}

// Singleton instance
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/group-buying/';

export const groupBuyingWS = new GroupBuyingWebSocket({
  url: WS_URL,
  reconnectInterval: 3000,
  maxReconnectAttempts: 5,
  heartbeatInterval: 30000,
});