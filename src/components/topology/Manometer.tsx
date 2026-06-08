interface ManometerProps {
  x: number;
  y: number;
  value: number;
  label: string;
}

export function Manometer({ x, y, value, label }: ManometerProps) {
  const normalized = Math.max(0, Math.min(1, value / 6));
  const angle = -135 + normalized * 270;
  const needleX = Math.cos((angle * Math.PI) / 180) * 17;
  const needleY = Math.sin((angle * Math.PI) / 180) * 17;

  return (
    <g transform={`translate(${x},${y})`}>
      <circle r="27" fill="hsl(0 0% 100%)" stroke="hsl(210 25% 78%)" strokeWidth="2" />
      <circle r="21" fill="hsl(210 45% 98%)" stroke="hsl(210 25% 88%)" />
      <path
        d="M -15 8 A 17 17 0 1 1 15 8"
        fill="none"
        stroke="hsl(205 70% 72%)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {[-120, -60, 0, 60, 120].map((tick) => {
        const inner = 14;
        const outer = 18;
        return (
          <line
            key={tick}
            x1={Math.cos((tick * Math.PI) / 180) * inner}
            y1={Math.sin((tick * Math.PI) / 180) * inner}
            x2={Math.cos((tick * Math.PI) / 180) * outer}
            y2={Math.sin((tick * Math.PI) / 180) * outer}
            stroke="hsl(215 20% 55%)"
            strokeWidth="1"
            strokeLinecap="round"
          />
        );
      })}
      <line
        x1="0"
        y1="0"
        x2={needleX}
        y2={needleY}
        stroke="hsl(var(--primary))"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle r="3" fill="hsl(var(--primary))" />
      <text
        x="0"
        y="39"
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="hsl(var(--foreground))"
        fontFamily="Inter, sans-serif"
      >
        {label} · {value.toFixed(1)} mca
      </text>
    </g>
  );
}

export default Manometer;
