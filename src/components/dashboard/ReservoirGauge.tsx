interface ReservoirGaugeProps {
  level: number;     // 0-100
  width?: number;
  height?: number;
}

export function ReservoirGauge({ level, width = 110, height = 170 }: ReservoirGaugeProps) {
  const fillH = (Math.max(0, Math.min(100, level)) / 100) * (height - 24);
  const waterY = 12 + (height - 24 - fillH);

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-label="Reservatório">
      <defs>
        <linearGradient id="rg-water" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.9" />
          <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="rg-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="hsl(210 25% 92%)" />
          <stop offset="100%" stopColor="hsl(210 25% 82%)" />
        </linearGradient>
        <clipPath id="rg-clip">
          <rect x="8" y="8" width={width - 16} height={height - 16} rx="14" />
        </clipPath>
      </defs>
      <rect
        x="4" y="4"
        width={width - 8} height={height - 8}
        rx="18"
        fill="url(#rg-body)"
        stroke="hsl(var(--border))" strokeWidth="1.5"
      />
      <g clipPath="url(#rg-clip)">
        <rect
          x="8" y={waterY}
          width={width - 16} height={fillH}
          fill="url(#rg-water)"
          style={{ transition: 'y 800ms cubic-bezier(0.22,1,0.36,1), height 800ms cubic-bezier(0.22,1,0.36,1)' }}
        />
        <path
          d={`M0 ${waterY} Q ${width / 4} ${waterY - 6} ${width / 2} ${waterY} T ${width} ${waterY} V ${height} H 0 Z`}
          fill="hsl(var(--primary-glow))"
          opacity="0.35"
          style={{ transition: 'all 800ms cubic-bezier(0.22,1,0.36,1)' }}
        >
          <animateTransform attributeName="transform" type="translate" from="-20 0" to="0 0" dur="3s" repeatCount="indefinite" />
        </path>
      </g>
      <rect
        x="4" y="4"
        width={width - 8} height={height - 8}
        rx="18"
        fill="none" stroke="white" strokeOpacity="0.4" strokeWidth="1"
      />
    </svg>
  );
}

export default ReservoirGauge;
