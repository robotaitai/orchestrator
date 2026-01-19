import { useEffect, useState, useCallback } from 'react';
import ChatPanel from './components/ChatPanel';
import MiniMap from './components/MiniMap';
import PlatformCards from './components/PlatformCards';
import Timeline from './components/Timeline';
import SimView from './components/SimView';
import { wsClient, fetchStatus, fetchDemoCommands, runDemoStep, resetDemo, exportReplay, loadReplay, type Platform, type Task, type TimelineEvent, type DemoCommand, type WSMessage } from './api';
import './App.css';

interface AppState {
  platforms: Record<string, Platform>;
  tasks: Task[];
  timeline: TimelineEvent[];
  connected: boolean;
  demoCommands: DemoCommand[];
  demoStep: number;
  demoScene: number;
  demoSceneName: string;
  demoRunning: boolean;
  demoAbort: boolean;
}

function App() {
  const [state, setState] = useState<AppState>({
    platforms: {},
    tasks: [],
    timeline: [],
    connected: false,
    demoCommands: [],
    demoStep: -1,
    demoScene: 0,
    demoSceneName: '',
    demoRunning: false,
    demoAbort: false,
  });

  // Fetch initial state
  useEffect(() => {
    fetchStatus().then(status => {
      setState(prev => ({
        ...prev,
        platforms: status.platforms,
        tasks: status.recent_tasks,
      }));
    });

    fetchDemoCommands().then(data => {
      setState(prev => ({ ...prev, demoCommands: data.commands }));
    });
  }, []);

  // WebSocket connection
  useEffect(() => {
    wsClient.connect();

    const unsubConnect = wsClient.on('connected', () => {
      setState(prev => ({ ...prev, connected: true }));
    });

    const unsubDisconnect = wsClient.on('disconnected', () => {
      setState(prev => ({ ...prev, connected: false }));
    });

    const unsubStateSync = wsClient.on('state_sync', (msg: WSMessage) => {
      if (msg.type === 'state_sync') {
        setState(prev => ({
          ...prev,
          platforms: msg.platforms,
          tasks: Object.values(msg.tasks),
          timeline: msg.timeline,
        }));
      }
    });

    const unsubPoses = wsClient.on('poses', (msg: WSMessage) => {
      if (msg.type === 'poses') {
        setState(prev => {
          const platforms = { ...prev.platforms };
          for (const [id, pose] of Object.entries(msg.platforms)) {
            if (platforms[id]) {
              platforms[id] = {
                ...platforms[id],
                position: { x: pose.x, y: pose.y, z: pose.z },
                status: pose.status as Platform['status'],
              };
            }
          }
          return { ...prev, platforms };
        });
      }
    });

    const unsubEvent = wsClient.on('timeline_event', (msg: WSMessage) => {
      if (msg.type === 'timeline_event') {
        setState(prev => ({
          ...prev,
          timeline: [...prev.timeline.slice(-99), msg.event],
        }));
      }
    });

    return () => {
      unsubConnect();
      unsubDisconnect();
      unsubStateSync();
      unsubPoses();
      unsubEvent();
      wsClient.disconnect();
    };
  }, []);

  // Demo mode with abort flag
  const startDemo = useCallback(async () => {
    setState(prev => ({ 
      ...prev, 
      demoRunning: true, 
      demoStep: 0, 
      demoAbort: false,
      demoScene: 0,
      demoSceneName: '',
    }));
    
    // Reset demo state (conversation + platform positions)
    try {
      await resetDemo();
    } catch (e) {
      console.error('Demo reset failed:', e);
    }

    const commands = state.demoCommands;
    
    for (let i = 0; i < commands.length; i++) {
      // Check abort flag
      const currentState = await new Promise<AppState>(resolve => {
        setState(prev => {
          resolve(prev);
          return prev;
        });
      });
      
      if (currentState.demoAbort) {
        console.log('Demo aborted');
        break;
      }
      
      const cmd = commands[i];
      setState(prev => ({ 
        ...prev, 
        demoStep: i,
        demoScene: cmd.scene || 0,
        demoSceneName: cmd.scene_name || '',
      }));
      
      try {
        console.log(`[Demo] Scene ${cmd.scene || 0}: ${cmd.scene_name || ''} - "${cmd.text}"`);
        const result = await runDemoStep(i);
        
        // Update scene info from result
        setState(prev => ({
          ...prev,
          demoScene: result.scene,
          demoSceneName: result.scene_name,
        }));
        
        // Wait for delay
        await new Promise(r => setTimeout(r, cmd.delay * 1000));
      } catch (e) {
        console.error('Demo step failed:', e);
      }
    }

    setState(prev => ({ 
      ...prev, 
      demoRunning: false, 
      demoStep: -1,
      demoScene: 0,
      demoSceneName: '',
      demoAbort: false,
    }));
  }, [state.demoCommands]);

  const stopDemo = useCallback(() => {
    setState(prev => ({ ...prev, demoAbort: true }));
  }, []);

  // Export replay
  const handleExport = useCallback(async () => {
    try {
      const result = await exportReplay();
      // Download as file
      const blob = new Blob([result.content], { type: 'application/jsonl' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `commander-replay-${new Date().toISOString().slice(0, 10)}.jsonl`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export failed:', e);
    }
  }, []);

  // Load replay from file
  const handleLoadReplay = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.jsonl,.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      
      try {
        const content = await file.text();
        const result = await loadReplay(content);
        console.log(`Loaded replay with ${result.event_count} events`);
        
        // Populate timeline with loaded events
        if (result.events && result.events.length > 0) {
          const events = result.events as Array<{
            event_type?: string;
            timestamp?: string;
            data?: Record<string, unknown>;
            task_id?: string;
            platform_id?: string;
          }>;
          setState(prev => ({
            ...prev,
            timeline: events.slice(-100).map((evt, idx) => ({
              id: `replay_${idx}`,
              type: evt.event_type || 'unknown',
              timestamp: evt.timestamp || new Date().toISOString(),
              data: evt.data || {},
              task_id: evt.task_id || null,
              platform_id: evt.platform_id || null,
            })),
          }));
        }
      } catch (e) {
        console.error('Load replay failed:', e);
      }
    };
    input.click();
  }, []);

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1>COMMANDER</h1>
          <span className="version">v0.1.0</span>
        </div>
        <div className="header-center">
          <div className={`status-indicator ${state.connected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot"></span>
            {state.connected ? 'CONNECTED' : 'DISCONNECTED'}
          </div>
        </div>
        <div className="header-right">
          <button 
            className="load-btn"
            onClick={handleLoadReplay}
            title="Load replay from JSONL file"
          >
            LOAD
          </button>
          <button 
            className="export-btn"
            onClick={handleExport}
            title="Export session as JSONL"
          >
            EXPORT
          </button>
          <button 
            className={`demo-btn ${state.demoRunning ? 'running' : ''}`}
            onClick={state.demoRunning ? stopDemo : startDemo}
            disabled={state.demoCommands.length === 0}
          >
            {state.demoRunning 
              ? `Scene ${state.demoScene}: ${state.demoSceneName} (${state.demoStep + 1}/${state.demoCommands.length})` 
              : 'START DEMO'}
          </button>
          {state.demoRunning && (
            <button className="stop-demo-btn" onClick={stopDemo}>
              STOP
            </button>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className="app-main">
        {/* Left column: Chat */}
        <aside className="panel-left">
          <ChatPanel />
        </aside>

        {/* Center: SimView + Timeline */}
        <section className="panel-center">
          <div className="sim-container">
            <SimView platforms={state.platforms} />
          </div>
          <div className="timeline-container">
            <Timeline events={state.timeline} />
          </div>
        </section>

        {/* Right column: MiniMap + Platform Cards */}
        <aside className="panel-right">
          <div className="minimap-container">
            <MiniMap platforms={state.platforms} />
          </div>
          <div className="cards-container">
            <PlatformCards platforms={state.platforms} />
          </div>
        </aside>
      </main>
    </div>
  );
}

export default App;
