import { useMemo } from 'react';
import type { TankGroup } from '../../types/telemetry';
import { LoraNode } from './LoraNode';
import { Manometer } from './Manometer';
import { MiniTank } from './MiniTank';

interface Props {
  tankGroups: TankGroup[];
  vazao?: number;
  vazao1?: number;
  vazao2?: number;
  pressao1?: number;
  pressao2?: number;
}

const GROUPS = [
  { x: 560, y: 72, centerX: 682, pipeX: 682, label: 'Grupo 1', manometerX: 734 },
  { x: 870, y: 72, centerX: 992, pipeX: 992, label: 'Grupo 2', manometerX: 1044 },
] as const;

function FlowPipe({
  d,
  width = 10,
  fast = false,
  muted = false,
}: {
  d: string;
  width?: number;
  fast?: boolean;
  muted?: boolean;
}) {
  return (
    <>
      <path
        d={d}
        stroke={muted ? 'url(#schema-pipe)' : 'url(#schema-pipe)'}
        strokeWidth={width}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d={d}
        stroke="hsl(var(--primary-glow))"
        strokeWidth={Math.max(2, width * 0.22)}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={fast ? 'schema-flow-fast' : 'schema-flow'}
        strokeDasharray={fast ? '10 12' : '8 10'}
        opacity={muted ? 0.65 : 0.95}
      />
    </>
  );
}

function ContextReservoir({ x, y, name }: { x: number; y: number; name: string }) {
  return (
    <g transform={`translate(${x},${y})`}>
      <title>{name} - 40.000 L - contexto sem sensor</title>
      <rect width="145" height="108" rx="8" fill="hsl(214 16% 88%)" stroke="hsl(214 12% 72%)" strokeWidth="1.5" />
      <rect x="8" y="-8" width="129" height="10" rx="3" fill="hsl(214 12% 76%)" />
      <line x1="15" y1="76" x2="130" y2="76" stroke="hsl(214 10% 68%)" strokeDasharray="4 5" />
      <text x="72.5" y="43" textAnchor="middle" fontSize="17" fontWeight="800" fill="hsl(214 12% 48%)" fontFamily="Inter, sans-serif">
        40.000 L
      </text>
      <text x="72.5" y="63" textAnchor="middle" fontSize="11" fontWeight="700" fill="hsl(214 12% 50%)" fontFamily="Inter, sans-serif">
        {name}
      </text>
      <text x="72.5" y="95" textAnchor="middle" fontSize="9" fill="hsl(214 10% 48%)" fontFamily="Inter, sans-serif">
        sem sensor
      </text>
    </g>
  );
}

function GroupBlock({
  group,
  index,
  vazao,
  pressao,
}: {
  group: TankGroup;
  index: 0 | 1;
  vazao: number;
  pressao: number;
}) {
  const layout = GROUPS[index];
  const tankGap = 13;
  const tankWidth = 50;
  const pipeDown = `M ${layout.pipeX} 210 L ${layout.pipeX} 330`;

  return (
    <g>
      <rect
        x={layout.x - 20}
        y={layout.y - 42}
        width="280"
        height="190"
        rx="10"
        fill="hsl(210 55% 98%)"
        stroke="hsl(210 36% 86%)"
      />
      <text
        x={layout.centerX}
        y={layout.y - 20}
        textAnchor="middle"
        fontSize="12"
        fontWeight="800"
        fill="hsl(var(--primary))"
        fontFamily="Inter, sans-serif"
        letterSpacing="0.08em"
      >
        {group.name.toUpperCase()} · 4x10.000 L
      </text>

      <LoraNode x={layout.x + 230} y={layout.y - 10} />
      <circle cx={layout.x + 18} cy={layout.y - 12} r="4" fill="hsl(var(--accent))" />
      <line
        x1={layout.x + 18}
        x2={layout.x + 18}
        y1={layout.y - 8}
        y2={layout.y + 90 - group.levelPct * 0.72}
        stroke="hsl(var(--accent))"
        strokeDasharray="3 4"
      />
      <text x={layout.x + 28} y={layout.y - 8} fontSize="9" fontWeight="700" fill="hsl(var(--foreground))" fontFamily="Inter, sans-serif">
        Sensor LV
      </text>

      {Array.from({ length: group.tanks }).map((_, tankIndex) => (
        <MiniTank
          key={`${group.id}-${tankIndex}`}
          x={layout.x + tankIndex * (tankWidth + tankGap)}
          y={layout.y + 18}
          pct={group.levelPct}
          id={`clip-${group.id}-${tankIndex}`}
          label={`T${tankIndex + 1}`}
        />
      ))}

      <FlowPipe d={pipeDown} width={10} />
      <polygon points={`${layout.pipeX},336 ${layout.pipeX - 7},321 ${layout.pipeX + 7},321`} fill="hsl(var(--primary-glow))" />
      <Manometer x={layout.manometerX} y={275} value={pressao} label={index === 0 ? 'P1' : 'P2'} />

      <g transform={`translate(${layout.pipeX - 48},340)`}>
        <rect width="96" height="26" rx="13" fill="hsl(205 80% 96%)" stroke="hsl(205 60% 78%)" />
        <text x="48" y="17" textAnchor="middle" fontSize="10" fontWeight="800" fill="hsl(var(--primary))" fontFamily="ui-monospace, monospace">
          {vazao.toFixed(1)} L/min
        </text>
      </g>
    </g>
  );
}

function Building() {
  return (
    <g>
      <image
        href="/imagem_hospital_3d.png"
        x="650"
        y="356"
        width="360"
        height="269"
        preserveAspectRatio="xMidYMid meet"
      />
    </g>
  );
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-full border border-border bg-card/95 px-3 py-1.5 text-xs shadow-soft">
      <span className="text-muted-foreground">{label}</span>
      <span className="ml-2 font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

export function HospitalHydraulicScheme({
  tankGroups,
  vazao = 0,
  vazao1,
  vazao2,
  pressao1 = 3.4,
  pressao2 = 3.2,
}: Props) {
  const [group1, group2] = tankGroups;
  const flow1 = vazao1 ?? vazao * 0.56;
  const flow2 = vazao2 ?? Math.max(0, vazao - flow1);
  const updatedAt = useMemo(
    () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    [],
  );

  if (!group1 || !group2) return null;

  return (
    <section className="rounded-3xl border border-border bg-card shadow-soft overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-4 px-6 pt-6 pb-4">
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            <span className="relative inline-flex h-2.5 w-2.5">
              <span className="absolute inset-0 rounded-full bg-[hsl(140_60%_50%)] opacity-60 schema-lora" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[hsl(140_60%_45%)]" />
            </span>
            Esquema hidráulico · tempo real
          </div>
          <h3 className="mt-1 text-2xl font-semibold text-foreground shimmer-text">
            Topologia da instalação
          </h3>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-primary-glow" />
            Alimentação
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-primary" />
            Distribuição
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[hsl(140_60%_45%)]" />
            LoRa
          </span>
          <span className="font-mono">atualizado {updatedAt}</span>
        </div>
      </div>

      <div className="relative mx-4 mb-6 overflow-x-auto rounded-2xl border border-border bg-card">
        <div className="pointer-events-none absolute right-4 top-4 z-10 hidden gap-2 lg:flex">
          <Pill label="Vazão total" value={`${(flow1 + flow2).toFixed(1)} L/min`} />
          <Pill label="Pressão" value={`${((pressao1 + pressao2) / 2).toFixed(2)} mca`} />
        </div>

        <svg
          viewBox="0 0 1200 620"
          className="block h-auto w-full min-w-[820px]"
          role="img"
          aria-label="Esquema hidráulico do Hospital Santa Ana"
        >
          <defs>
            <pattern id="schema-grid" width="28" height="28" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="1" fill="hsl(var(--border))" opacity="0.65" />
            </pattern>
            <linearGradient id="schema-bg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="hsl(0 0% 100%)" />
              <stop offset="100%" stopColor="hsl(210 55% 97%)" />
            </linearGradient>
            <linearGradient id="schema-water" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(195 90% 72%)" />
              <stop offset="62%" stopColor="hsl(var(--primary-glow))" />
              <stop offset="100%" stopColor="hsl(var(--primary))" />
            </linearGradient>
            <linearGradient id="schema-pipe" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(210 18% 82%)" />
              <stop offset="50%" stopColor="hsl(210 18% 96%)" />
              <stop offset="100%" stopColor="hsl(210 18% 70%)" />
            </linearGradient>
            <radialGradient id="schema-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.16" />
              <stop offset="100%" stopColor="hsl(var(--primary-glow))" stopOpacity="0" />
            </radialGradient>
          </defs>

          <rect width="1200" height="620" fill="url(#schema-bg)" />
          <rect width="1200" height="620" fill="url(#schema-grid)" />
          <ellipse cx="230" cy="505" rx="250" ry="82" fill="url(#schema-glow)" />
          <ellipse cx="920" cy="150" rx="320" ry="105" fill="url(#schema-glow)" />

          <FlowPipe d="M 197 466 L 197 420" width={11} />
          <FlowPipe d="M 197 366 L 197 146" width={11} />
          <FlowPipe d="M 197 146 L 115 146" width={10} />
          <FlowPipe d="M 197 146 L 278 146" width={10} />
          <FlowPipe d="M 350 146 L 560 146" width={12} fast />
          <FlowPipe d="M 682 205 L 1018 205" width={12} fast />
          <FlowPipe d="M 682 205 L 682 90" width={9} fast />
          <FlowPipe d="M 992 205 L 992 90" width={9} fast />
          <g transform="translate(136,466)">
            <rect width="122" height="66" rx="10" fill="hsl(var(--primary))" />
            <text x="61" y="20" textAnchor="middle" fontSize="9" fill="hsl(210 35% 88%)" letterSpacing="0.18em" fontFamily="Inter, sans-serif">
              REDE
            </text>
            <text x="61" y="42" textAnchor="middle" fontSize="15" fontWeight="900" fill="white" fontFamily="Inter, sans-serif">
              SABESP
            </text>
            <text x="61" y="58" textAnchor="middle" fontSize="8.5" fill="hsl(210 35% 86%)" fontFamily="Inter, sans-serif">
              entrada
            </text>
          </g>

          <g transform="translate(166,366)">
            <circle cx="31" cy="31" r="31" fill="hsl(210 30% 96%)" stroke="hsl(210 18% 70%)" strokeWidth="2" />
            <circle cx="31" cy="31" r="20" fill="white" stroke="hsl(210 18% 68%)" strokeDasharray="4 3" />
            <text x="31" y="35" textAnchor="middle" fontSize="10" fontWeight="900" fill="hsl(var(--primary))" fontFamily="ui-monospace, monospace">
              m³
            </text>
            <text x="31" y="72" textAnchor="middle" fontSize="9" fontWeight="800" fill="hsl(var(--foreground))" fontFamily="Inter, sans-serif">
              HIDRÔMETRO
            </text>
          </g>

          <text x="196" y="46" textAnchor="middle" fontSize="10" fontWeight="900" fill="hsl(214 12% 42%)" fontFamily="Inter, sans-serif" letterSpacing="0.08em">
            RESERVATÓRIOS DE RECALQUE
          </text>
          <text x="196" y="62" textAnchor="middle" fontSize="9" fontWeight="700" fill="hsl(214 10% 50%)" fontFamily="Inter, sans-serif">
            contexto hidráulico · sem sensor
          </text>
          <ContextReservoir x={42} y={92} name="Recalque 1" />
          <ContextReservoir x={205} y={92} name="Recalque 2" />

          <text x="742" y="196" textAnchor="middle" fontSize="10" fontWeight="700" fill="hsl(var(--primary))" fontFamily="Inter, sans-serif">
            manifold superior
          </text>

          <GroupBlock group={group1} index={0} vazao={flow1} pressao={pressao1} />
          <GroupBlock group={group2} index={1} vazao={flow2} pressao={pressao2} />

          <Building />
          <FlowPipe d="M 682 330 L 682 376 L 830 376" width={10} />
          <FlowPipe d="M 992 330 L 992 376 L 830 376" width={10} />
          <text x="830" y="366" textAnchor="middle" fontSize="11" fontWeight="800" fill="hsl(var(--primary))" fontFamily="Inter, sans-serif">
            distribuição por gravidade
          </text>
        </svg>
      </div>
    </section>
  );
}

export default HospitalHydraulicScheme;
