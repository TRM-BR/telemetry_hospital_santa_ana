interface MiniTankProps {
  x: number;
  y: number;
  pct: number;
  id: string;
  label: string;
}

const WIDTH = 50;
const HEIGHT = 102;

export function MiniTank({ x, y, pct, id, label }: MiniTankProps) {
  const safePct = Math.max(0, Math.min(100, pct));
  const fillHeight = Math.max(6, (safePct / 100) * (HEIGHT - 8));
  const fillY = y + HEIGHT - fillHeight - 4;

  return (
    <g transform={`translate(${x},${y})`}>
      <title>
        {label} - {safePct}% - 10.000 L
      </title>
      <rect x="-2" y="-7" width={WIDTH + 4} height="7" rx="2.5" fill="hsl(var(--primary-deep))" />
      <rect
        width={WIDTH}
        height={HEIGHT}
        rx="5"
        fill="hsl(220 42% 26%)"
        stroke="hsl(220 30% 44%)"
        strokeWidth="1.4"
      />
      <clipPath id={id}>
        <rect x="3" y={HEIGHT - fillHeight - 3} width={WIDTH - 6} height={fillHeight} rx="3" />
      </clipPath>
      <g clipPath={`url(#${id})`}>
        <rect x="3" y={HEIGHT - fillHeight - 3} width={WIDTH - 6} height={fillHeight} fill="url(#schema-water)" />
        <path
          d={`M -14 ${HEIGHT - fillHeight - 3} Q 8 ${HEIGHT - fillHeight - 8} 27 ${HEIGHT - fillHeight - 3} T 68 ${HEIGHT - fillHeight - 3} V ${HEIGHT} H -14 Z`}
          fill="hsl(var(--primary-glow))"
          opacity="0.42"
          className="schema-tank-wave"
        />
      </g>
      <line
        x1="0"
        x2="7"
        y1={HEIGHT * 0.25}
        y2={HEIGHT * 0.25}
        stroke="hsl(210 28% 75%)"
        strokeWidth="1"
      />
      <line
        x1="0"
        x2="7"
        y1={HEIGHT * 0.5}
        y2={HEIGHT * 0.5}
        stroke="hsl(210 28% 75%)"
        strokeWidth="1"
      />
      <line
        x1="0"
        x2="7"
        y1={HEIGHT * 0.75}
        y2={HEIGHT * 0.75}
        stroke="hsl(210 28% 75%)"
        strokeWidth="1"
      />
      <text
        x={WIDTH / 2}
        y={HEIGHT + 18}
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="hsl(var(--muted-foreground))"
        fontFamily="Inter, sans-serif"
      >
        {label}
      </text>
      <text
        x={WIDTH / 2}
        y={Math.max(18, fillY - y + fillHeight / 2 + 3)}
        textAnchor="middle"
        fontSize="10"
        fontWeight="800"
        fill="white"
        fontFamily="Inter, sans-serif"
      >
        {safePct}%
      </text>
    </g>
  );
}

export default MiniTank;
