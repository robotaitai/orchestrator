import { useEffect, useState, useRef } from 'react';
import { wsClient, type Platform, type WSMessage } from '../api';
import './SimView.css';

interface SimViewProps {
  platforms: Record<string, Platform>;
}

export default function SimView({ platforms }: SimViewProps) {
  const platformList = Object.values(platforms);
  const [frameData, setFrameData] = useState<string | null>(null);
  const [framesEnabled, setFramesEnabled] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);

  // Subscribe to frame updates
  useEffect(() => {
    const handleFrame = (msg: WSMessage) => {
      if (msg.type === 'frame' && 'data' in msg) {
        setFrameData(msg.data as string);
        setFrameCount(c => c + 1);
      }
    };

    const unsubFrame = wsClient.on('frame', handleFrame);

    // Enable frame streaming when component mounts
    if (wsClient.isConnected) {
      wsClient.send({ type: 'enable_frames', enabled: true });
      setFramesEnabled(true);
    }

    return () => {
      unsubFrame();
      // Disable frame streaming when unmounting
      if (wsClient.isConnected) {
        wsClient.send({ type: 'enable_frames', enabled: false });
      }
    };
  }, []);

  // Toggle frame streaming
  const toggleFrames = () => {
    const newState = !framesEnabled;
    wsClient.send({ type: 'enable_frames', enabled: newState });
    setFramesEnabled(newState);
    if (!newState) {
      setFrameData(null);
    }
  };

  return (
    <div className="sim-view">
      <div className="sim-header">
        <span className="sim-title">3D SIMULATION VIEW</span>
        <div className="sim-header-right">
          {frameData && (
            <span className="frame-counter">Frame #{frameCount}</span>
          )}
          <button 
            className={`frame-toggle ${framesEnabled ? 'enabled' : ''}`}
            onClick={toggleFrames}
          >
            {framesEnabled ? 'STREAMING' : 'SVG MODE'}
          </button>
          <span className="sim-status">
            {frameData ? 'MuJoCo Live' : 'SVG Fallback'}
          </span>
        </div>
      </div>

      <div className="sim-viewport">
        {frameData ? (
          // MuJoCo rendered frame
          <img
            ref={imgRef}
            src={`data:image/jpeg;base64,${frameData}`}
            alt="MuJoCo Simulation"
            className="sim-frame"
          />
        ) : (
          // SVG fallback visualization
          <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid meet" className="sim-svg">
            <defs>
              <linearGradient id="groundGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(0, 212, 170, 0.05)" />
                <stop offset="100%" stopColor="rgba(99, 102, 241, 0.05)" />
              </linearGradient>
              <linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgba(99, 102, 241, 0.1)" />
                <stop offset="100%" stopColor="transparent" />
              </linearGradient>
            </defs>

            {/* Sky gradient */}
            <rect x="0" y="0" width="400" height="150" fill="url(#skyGrad)" />

            {/* Ground plane (isometric) */}
            <polygon
              points="200,100 380,200 200,280 20,200"
              fill="url(#groundGrad)"
              stroke="var(--color-border)"
              strokeWidth="1"
            />

            {/* Grid lines */}
            <g stroke="var(--color-border)" strokeWidth="0.3" opacity="0.5">
              {[0, 1, 2, 3, 4].map(i => (
                <line
                  key={`h${i}`}
                  x1={60 + i * 35}
                  y1={140 + i * 18}
                  x2={340 - i * 35}
                  y2={140 + i * 18}
                />
              ))}
              {[0, 1, 2, 3, 4].map(i => (
                <line
                  key={`v${i}`}
                  x1={200 - 90 + i * 45}
                  y1={100 + i * 9}
                  x2={200 - 90 + i * 45 - 90}
                  y2={190 + i * 9}
                />
              ))}
            </g>

            {/* Axis indicator */}
            <g transform="translate(50, 250)">
              <line x1="0" y1="0" x2="25" y2="-12" stroke="var(--color-error)" strokeWidth="2" />
              <line x1="0" y1="0" x2="25" y2="12" stroke="var(--color-success)" strokeWidth="2" />
              <line x1="0" y1="0" x2="0" y2="-25" stroke="var(--color-info)" strokeWidth="2" />
              <text x="30" y="-10" fontSize="8" fill="var(--color-error)">X</text>
              <text x="30" y="15" fontSize="8" fill="var(--color-success)">Y</text>
              <text x="5" y="-25" fontSize="8" fill="var(--color-info)">Z</text>
            </g>

            {/* Platforms */}
            {platformList.map((platform) => {
              const scale = 2;
              const baseX = 200;
              const baseY = 190;
              const isoX = baseX + (platform.position.x - platform.position.y) * scale;
              const isoY = baseY + (platform.position.x + platform.position.y) * scale * 0.5 - platform.position.z * 2;

              const isUAV = platform.type === 'uav';
              const color = isUAV ? 'var(--color-uav)' : 'var(--color-ugv)';
              const isActive = platform.status !== 'idle';

              return (
                <g key={platform.id} className={`sim-platform ${platform.status}`}>
                  {isUAV && (
                    <ellipse
                      cx={isoX}
                      cy={baseY + (platform.position.x + platform.position.y) * scale * 0.5}
                      rx="8"
                      ry="4"
                      fill="rgba(0,0,0,0.3)"
                    />
                  )}

                  {isUAV ? (
                    <g transform={`translate(${isoX}, ${isoY})`}>
                      <ellipse cx="0" cy="0" rx="10" ry="6" fill={color} />
                      <line x1="-12" y1="-5" x2="12" y2="5" stroke={color} strokeWidth="2" />
                      <line x1="12" y1="-5" x2="-12" y2="5" stroke={color} strokeWidth="2" />
                      <circle cx="-12" cy="-5" r="4" fill="none" stroke={color} strokeWidth="1" className={isActive ? 'rotor' : ''} />
                      <circle cx="12" cy="-5" r="4" fill="none" stroke={color} strokeWidth="1" className={isActive ? 'rotor' : ''} />
                      <circle cx="-12" cy="5" r="4" fill="none" stroke={color} strokeWidth="1" className={isActive ? 'rotor' : ''} />
                      <circle cx="12" cy="5" r="4" fill="none" stroke={color} strokeWidth="1" className={isActive ? 'rotor' : ''} />
                    </g>
                  ) : (
                    <g transform={`translate(${isoX}, ${isoY})`}>
                      <rect x="-12" y="-8" width="24" height="16" rx="3" fill={color} />
                      <circle cx="-8" cy="8" r="4" fill="var(--color-bg)" stroke={color} strokeWidth="1" />
                      <circle cx="8" cy="8" r="4" fill="var(--color-bg)" stroke={color} strokeWidth="1" />
                    </g>
                  )}

                  <text
                    x={isoX}
                    y={isoY + (isUAV ? 20 : 25)}
                    fontSize="9"
                    fontWeight="600"
                    fill={color}
                    textAnchor="middle"
                    fontFamily="var(--font-mono)"
                  >
                    {platform.id.toUpperCase()}
                  </text>

                  {isActive && (
                    <circle
                      cx={isoX + (isUAV ? 12 : 15)}
                      cy={isoY - (isUAV ? 8 : 10)}
                      r="4"
                      fill={platform.status === 'error' ? 'var(--color-error)' : 'var(--color-success)'}
                      className="status-indicator"
                    />
                  )}
                </g>
              );
            })}

            <text x="200" y="25" fontSize="12" fontWeight="700" fill="var(--color-primary)" textAnchor="middle" letterSpacing="0.2em">
              COMMANDER DEMO
            </text>
          </svg>
        )}
      </div>

      <div className="sim-controls">
        <div className="sim-stat">
          <span className="stat-label">Platforms</span>
          <span className="stat-value">{platformList.length}</span>
        </div>
        <div className="sim-stat">
          <span className="stat-label">Active</span>
          <span className="stat-value">{platformList.filter(p => p.status !== 'idle').length}</span>
        </div>
        <div className="sim-stat">
          <span className="stat-label">UGVs</span>
          <span className="stat-value">{platformList.filter(p => p.type === 'ugv').length}</span>
        </div>
        <div className="sim-stat">
          <span className="stat-label">UAVs</span>
          <span className="stat-value">{platformList.filter(p => p.type === 'uav').length}</span>
        </div>
      </div>
    </div>
  );
}
