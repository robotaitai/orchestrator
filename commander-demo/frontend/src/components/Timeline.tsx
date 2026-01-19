import { useRef, useEffect } from 'react';
import type { TimelineEvent } from '../api';
import './Timeline.css';

interface TimelineProps {
  events: TimelineEvent[];
}

const eventIcons: Record<string, string> = {
  task_created: '📋',
  task_started: '▶️',
  task_succeeded: '✅',
  task_failed: '❌',
  task_cancelled: '⏹️',
  platform_state_changed: '📍',
  constraint_violation: '⚠️',
  system: '⚙️',
};

const eventColors: Record<string, string> = {
  task_created: 'var(--color-info)',
  task_started: 'var(--color-primary)',
  task_succeeded: 'var(--color-success)',
  task_failed: 'var(--color-error)',
  task_cancelled: 'var(--color-text-muted)',
  platform_state_changed: 'var(--color-secondary)',
  constraint_violation: 'var(--color-warning)',
  system: 'var(--color-text-muted)',
};

export default function Timeline({ events }: TimelineProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [events]);

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    });
  };

  const formatEventData = (event: TimelineEvent): string => {
    const data = event.data;
    if (data.command) return data.command as string;
    if (data.message) return (data.message as string).slice(0, 30);
    if (data.error) return `Error: ${(data.error as string).slice(0, 20)}`;
    return event.type.replace(/_/g, ' ');
  };

  // Take last 50 events
  const recentEvents = events.slice(-50);

  return (
    <div className="timeline">
      <div className="timeline-header">
        <span className="timeline-title">EVENT TIMELINE</span>
        <span className="timeline-count">{events.length} events</span>
      </div>

      <div className="timeline-scroll" ref={scrollRef}>
        <div className="timeline-track">
          {recentEvents.map((event, index) => (
            <div
              key={event.id}
              className={`timeline-event animate-fade-in`}
              style={{ 
                animationDelay: `${index * 0.02}s`,
                '--event-color': eventColors[event.type] || 'var(--color-text-muted)',
              } as React.CSSProperties}
            >
              <div className="event-time">{formatTime(event.timestamp)}</div>
              <div className="event-dot" />
              <div className="event-content">
                <span className="event-icon">{eventIcons[event.type] || '•'}</span>
                <span className="event-text">{formatEventData(event)}</span>
              </div>
              {event.task_id && (
                <div className="event-trace">
                  <code>{event.task_id}</code>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
