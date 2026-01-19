/**
 * API client for Commander backend
 */

const API_BASE = '/api/v1';

export interface Position {
  x: number;
  y: number;
  z: number;
}

export interface Platform {
  id: string;
  name: string;
  type: 'ugv' | 'uav';
  position: Position;
  status: 'idle' | 'moving' | 'executing' | 'holding' | 'error' | 'offline';
  battery_pct: number;
  health_ok: boolean;
}

export interface Task {
  id: string;
  command: string;
  target: string;
  params: Record<string, unknown>;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  progress: number;
}

export interface TimelineEvent {
  id: string;
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
  task_id: string | null;
  platform_id: string | null;
}

export interface CommandResult {
  trace_id: string;
  type: string;
  commands?: Array<{ command: string; target: string; params: Record<string, unknown> }>;
  tasks?: Array<{ id: string; status: string; error: string | null }>;
  explanation?: string;
  question?: string;
  options?: string[];
  message?: string;
  error?: string;
  details?: string;
}

export interface DemoCommand {
  text: string;
  delay: number;
  scene?: number;
  scene_name?: string;
}

export interface DemoScene {
  scene: number;
  name: string;
  commands: Array<{ text: string; delay: number }>;
}

export interface DemoStepResult {
  step: number;
  scene: number;
  scene_name: string;
  text: string;
  delay: number;
  result: CommandResult;
}

// ─────────────────────────────────────────────────────────────────────────────
// HTTP API
// ─────────────────────────────────────────────────────────────────────────────

export async function sendCommand(text: string): Promise<CommandResult> {
  const response = await fetch(`${API_BASE}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, execute: true }),
  });
  return response.json();
}

export async function fetchPlatforms(): Promise<{ platforms: Platform[]; count: number }> {
  const response = await fetch(`${API_BASE}/platforms`);
  return response.json();
}

export async function fetchStatus(): Promise<{
  platforms: Record<string, Platform>;
  tasks: { total: number; queued: number; running: number; succeeded: number; failed: number };
  recent_tasks: Task[];
  timeline_count: number;
}> {
  const response = await fetch(`${API_BASE}/status`);
  return response.json();
}

export async function fetchTimeline(limit = 50): Promise<{ events: TimelineEvent[]; count: number }> {
  const response = await fetch(`${API_BASE}/timeline?limit=${limit}`);
  return response.json();
}

export async function fetchDemoCommands(): Promise<{ commands: DemoCommand[] }> {
  const response = await fetch(`${API_BASE}/demo/commands`);
  return response.json();
}

export async function fetchDemoScript(): Promise<{ scenes: DemoScene[]; total_steps: number; total_scenes: number }> {
  const response = await fetch(`${API_BASE}/demo/script`);
  return response.json();
}

export async function runDemoStep(step: number): Promise<DemoStepResult> {
  const response = await fetch(`${API_BASE}/demo/run/${step}`, { method: 'POST' });
  return response.json();
}

export async function resetChat(): Promise<void> {
  await fetch(`${API_BASE}/chat/reset`, { method: 'POST' });
}

export async function resetDemo(): Promise<void> {
  await fetch(`${API_BASE}/demo/reset`, { method: 'POST' });
}

export async function fetchConstraints(): Promise<{
  min_separation_m: number;
  speed_limits: { ugv: number; uav: number };
  world_bounds: { x: number[]; y: number[]; z: number[] };
  no_go_zones: Array<{ name: string; vertices: number[][] }>;
}> {
  const response = await fetch(`${API_BASE}/constraints`);
  return response.json();
}

export async function exportReplay(): Promise<{ event_count: number; content: string }> {
  const response = await fetch(`${API_BASE}/replay/export`);
  return response.json();
}

export async function loadReplay(content: string): Promise<{ status: string; event_count: number; events: unknown[] }> {
  const response = await fetch(`${API_BASE}/replay/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'text/plain' },
    body: content,
  });
  return response.json();
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────────────────────────

export type WSMessage =
  | { type: 'state_sync'; platforms: Record<string, Platform>; tasks: Record<string, Task>; timeline: TimelineEvent[] }
  | { type: 'poses'; platforms: Record<string, { x: number; y: number; z: number; status: string }> }
  | { type: 'timeline_event'; event: TimelineEvent }
  | { type: 'command_result'; task_id: string; status: string; error: string | null }
  | { type: 'pong'; timestamp: string }
  | { type: 'frame'; data: string; timestamp: string }
  | { type: 'frames_enabled'; enabled: boolean };

export class CommanderWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, ((data: WSMessage) => void)[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;

  connect(): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
      this.emit('connected', {} as WSMessage);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WSMessage;
        this.emit(data.type, data);
        this.emit('message', data);
      } catch (e) {
        console.error('Failed to parse WS message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.emit('disconnected', {} as WSMessage);
      this.tryReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  private tryReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.min(this.reconnectAttempts, 5);
      console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
      setTimeout(() => this.connect(), delay);
    }
  }

  on(eventType: string, handler: (data: WSMessage) => void): () => void {
    const handlers = this.handlers.get(eventType) || [];
    handlers.push(handler);
    this.handlers.set(eventType, handlers);
    return () => this.off(eventType, handler);
  }

  off(eventType: string, handler: (data: WSMessage) => void): void {
    const handlers = this.handlers.get(eventType) || [];
    const index = handlers.indexOf(handler);
    if (index !== -1) {
      handlers.splice(index, 1);
      this.handlers.set(eventType, handlers);
    }
  }

  private emit(eventType: string, data: WSMessage): void {
    const handlers = this.handlers.get(eventType) || [];
    handlers.forEach(handler => handler(data));
  }

  send(data: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect(): void {
    this.maxReconnectAttempts = 0; // Prevent reconnect
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new CommanderWebSocket();
