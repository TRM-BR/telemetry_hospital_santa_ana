interface PumpSymbolProps {
  x: number;
  y: number;
  label: string;
}

export function PumpSymbol({ x, y, label }: PumpSymbolProps) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle
        cx="22"
        cy="22"
        r="22"
        fill="hsl(220 45% 96%)"
        stroke="hsl(var(--primary))"
        strokeWidth="2"
      />
      <g className="schema-node-breath">
        <path
          d="M 13 13 L 31 31 M 31 13 L 13 31"
          stroke="hsl(var(--primary-deep))"
          strokeWidth="4"
          strokeLinecap="round"
        />
      </g>
      <circle cx="22" cy="22" r="5" fill="hsl(var(--primary-glow))" opacity="0.9" />
      <text
        x="22"
        y="58"
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="hsl(var(--primary))"
        fontFamily="Inter, sans-serif"
      >
        {label}
      </text>
    </g>
  );
}

export default PumpSymbol;
