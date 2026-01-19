import type { Platform } from '../api';
import './PlatformCards.css';

interface PlatformCardsProps {
  platforms: Record<string, Platform>;
}

const statusLabels: Record<string, string> = {
  idle: 'IDLE',
  moving: 'MOVING',
  executing: 'EXEC',
  holding: 'HOLD',
  error: 'ERROR',
  offline: 'OFFLINE',
};

export default function PlatformCards({ platforms }: PlatformCardsProps) {
  const platformList = Object.values(platforms);
  const ugvs = platformList.filter(p => p.type === 'ugv');
  const uavs = platformList.filter(p => p.type === 'uav');

  return (
    <div className="platform-cards">
      <div className="cards-header">
        <span className="cards-title">FLEET STATUS</span>
        <span className="cards-count">{platformList.length} units</span>
      </div>

      <div className="cards-section">
        <div className="section-header ugv">
          <span className="section-icon">▣</span>
          <span>GROUND (UGV)</span>
          <span className="section-count">{ugvs.length}</span>
        </div>
        {ugvs.map(platform => (
          <PlatformCard key={platform.id} platform={platform} />
        ))}
      </div>

      <div className="cards-section">
        <div className="section-header uav">
          <span className="section-icon">△</span>
          <span>AERIAL (UAV)</span>
          <span className="section-count">{uavs.length}</span>
        </div>
        {uavs.map(platform => (
          <PlatformCard key={platform.id} platform={platform} />
        ))}
      </div>
    </div>
  );
}

function PlatformCard({ platform }: { platform: Platform }) {
  const isActive = platform.status !== 'idle' && platform.status !== 'offline';

  return (
    <div className={`platform-card ${platform.type} ${platform.status} ${isActive ? 'active' : ''}`}>
      <div className="card-header">
        <span className="card-id">{platform.id.toUpperCase()}</span>
        <span className={`card-status ${platform.status}`}>
          {statusLabels[platform.status] || platform.status}
        </span>
      </div>

      <div className="card-name">{platform.name}</div>

      <div className="card-stats">
        <div className="stat">
          <span className="stat-label">POS</span>
          <span className="stat-value mono">
            {platform.position.x.toFixed(1)}, {platform.position.y.toFixed(1)}
            {platform.type === 'uav' && `, ${platform.position.z.toFixed(1)}`}
          </span>
        </div>

        {platform.type === 'uav' && (
          <div className="stat">
            <span className="stat-label">ALT</span>
            <span className="stat-value mono">{platform.position.z.toFixed(1)}m</span>
          </div>
        )}

        <div className="stat">
          <span className="stat-label">BAT</span>
          <div className="battery-bar">
            <div
              className={`battery-fill ${platform.battery_pct < 20 ? 'low' : ''}`}
              style={{ width: `${platform.battery_pct}%` }}
            />
          </div>
          <span className="stat-value mono">{platform.battery_pct}%</span>
        </div>
      </div>

      {!platform.health_ok && (
        <div className="card-alert">⚠️ Health check failed</div>
      )}
    </div>
  );
}
