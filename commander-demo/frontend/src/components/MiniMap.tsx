import { useEffect, useState } from 'react';
import { fetchConstraints, type Platform } from '../api';
import './MiniMap.css';

interface MiniMapProps {
  platforms: Record<string, Platform>;
}

interface Constraints {
  world_bounds: { x: number[]; y: number[]; z: number[] };
  no_go_zones: Array<{ name: string; vertices: number[][] }>;
}

export default function MiniMap({ platforms }: MiniMapProps) {
  const [constraints, setConstraints] = useState<Constraints | null>(null);

  useEffect(() => {
    fetchConstraints().then(setConstraints);
  }, []);

  // Map coordinates to SVG viewport
  const bounds = constraints?.world_bounds || { x: [-50, 50], y: [-50, 50], z: [0, 30] };
  const mapToSvg = (x: number, y: number) => {
    const svgX = ((x - bounds.x[0]) / (bounds.x[1] - bounds.x[0])) * 100;
    const svgY = 100 - ((y - bounds.y[0]) / (bounds.y[1] - bounds.y[0])) * 100;
    return { x: svgX, y: svgY };
  };

  // Named locations
  const locations = [
    { name: 'α', x: 20, y: 30, label: 'Alpha' },
    { name: 'β', x: 40, y: 50, label: 'Bravo' },
    { name: 'γ', x: 10, y: -20, label: 'Charlie' },
    { name: 'H', x: 0, y: 0, label: 'Home' },
  ];

  return (
    <div className="minimap">
      <div className="minimap-header">
        <span className="minimap-title">TACTICAL MAP</span>
        <span className="minimap-bounds">
          [{bounds.x[0]}, {bounds.x[1]}] × [{bounds.y[0]}, {bounds.y[1]}]
        </span>
      </div>
      
      <div className="minimap-view">
        <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
          {/* Grid */}
          <defs>
            <pattern id="grid" width="10" height="10" patternUnits="userSpaceOnUse">
              <path d="M 10 0 L 0 0 0 10" fill="none" stroke="var(--color-border)" strokeWidth="0.3" />
            </pattern>
          </defs>
          <rect width="100" height="100" fill="url(#grid)" />

          {/* No-go zones */}
          {constraints?.no_go_zones.map((zone, i) => {
            const points = zone.vertices
              .map(([x, y]) => mapToSvg(x, y))
              .map(p => `${p.x},${p.y}`)
              .join(' ');
            return (
              <g key={i}>
                <polygon
                  points={points}
                  fill="var(--color-no-go)"
                  stroke="var(--color-error)"
                  strokeWidth="0.5"
                  strokeDasharray="2,2"
                />
                <text
                  x={mapToSvg(zone.vertices[0][0], zone.vertices[0][1]).x}
                  y={mapToSvg(zone.vertices[0][0], zone.vertices[0][1]).y - 2}
                  fontSize="4"
                  fill="var(--color-error)"
                >
                  {zone.name}
                </text>
              </g>
            );
          })}

          {/* Locations */}
          {locations.map(loc => {
            const pos = mapToSvg(loc.x, loc.y);
            return (
              <g key={loc.name}>
                <circle cx={pos.x} cy={pos.y} r="2" fill="none" stroke="var(--color-text-muted)" strokeWidth="0.5" />
                <text x={pos.x} y={pos.y + 1} fontSize="3" fill="var(--color-text-muted)" textAnchor="middle">
                  {loc.name}
                </text>
              </g>
            );
          })}

          {/* Platforms */}
          {Object.values(platforms).map(platform => {
            const pos = mapToSvg(platform.position.x, platform.position.y);
            const isUAV = platform.type === 'uav';
            const color = isUAV ? 'var(--color-uav)' : 'var(--color-ugv)';

            return (
              <g key={platform.id} className={`platform-marker ${platform.status}`}>
                {isUAV ? (
                  <>
                    <polygon
                      points={`${pos.x},${pos.y - 3} ${pos.x + 2.5},${pos.y + 2} ${pos.x - 2.5},${pos.y + 2}`}
                      fill={color}
                      stroke="white"
                      strokeWidth="0.3"
                    />
                    {/* Altitude indicator */}
                    <line
                      x1={pos.x}
                      y1={pos.y + 2}
                      x2={pos.x}
                      y2={pos.y + 2 + platform.position.z / 5}
                      stroke={color}
                      strokeWidth="0.5"
                      strokeDasharray="1,1"
                    />
                  </>
                ) : (
                  <rect
                    x={pos.x - 2}
                    y={pos.y - 2}
                    width="4"
                    height="4"
                    rx="0.5"
                    fill={color}
                    stroke="white"
                    strokeWidth="0.3"
                  />
                )}
                <text
                  x={pos.x}
                  y={pos.y + 6}
                  fontSize="3"
                  fill={color}
                  textAnchor="middle"
                  fontWeight="600"
                >
                  {platform.id.toUpperCase()}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="minimap-legend">
        <span className="legend-item ugv">
          <span className="legend-shape square"></span>UGV
        </span>
        <span className="legend-item uav">
          <span className="legend-shape triangle"></span>UAV
        </span>
        <span className="legend-item nogo">
          <span className="legend-shape zone"></span>No-Go
        </span>
      </div>
    </div>
  );
}
