interface LoraNodeProps {
  x: number;
  y: number;
  label?: string;
}

export function LoraNode({ x, y, label = 'LoRa' }: LoraNodeProps) {
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r="14" fill="hsl(140 70% 96%)" stroke="hsl(140 60% 48%)" strokeWidth="1.5" />
      <circle r="14" fill="none" stroke="hsl(140 60% 50%)" strokeWidth="1.5" className="schema-lora" />
      <circle r="4" fill="hsl(140 60% 45%)" className="schema-node-breath" />
      <path
        d="M -7 -3 Q 0 -10 7 -3 M -10 -8 Q 0 -18 10 -8"
        fill="none"
        stroke="hsl(140 55% 38%)"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.85"
      />
      <text
        x="0"
        y="30"
        textAnchor="middle"
        fontSize="9"
        fontWeight="700"
        fill="hsl(140 55% 32%)"
        fontFamily="Inter, sans-serif"
      >
        {label}
      </text>
    </g>
  );
}

export default LoraNode;
