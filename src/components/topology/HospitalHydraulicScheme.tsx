/**
 * Esquema Hidráulico — Hospital Santa Ana
 *
 * Layout (top → bottom):
 *   [Grupo 1 — 4 caixas 10.000 L]   [Grupo 2 — 4 caixas 10.000 L]  ← MONITORADOS
 *           ↑ Recalque (bomba)               ↑ Recalque (bomba)
 *   [Recalque 1 — 40.000 L]         [Recalque 2 — 40.000 L]         ← NÃO monitorados
 *   [SABESP] → [Hidrômetro principal] → (alimenta recalques)
 *           ↓ Distribuição por gravidade ↓
 *   [Hospital Santa Ana — prédio]
 *
 * Pintado inteiramente em SVG + Tailwind.
 * Dados vêm do mock centralizado — sem API real nesta etapa.
 */

import type { HospitalMockData } from '../../types/telemetry';

interface Props {
  data: HospitalMockData;
}

// ── Geometria das caixas superiores ──────────────────────────
const TANK_W = 90;
const TANK_H = 180;
const TANK_Y = 52;

const G1_TANKS = [72, 172, 272, 372] as const;
const G2_TANKS = [737, 837, 937, 1037] as const;

function waterY(levelPct: number): number {
  return TANK_Y + TANK_H - Math.round((levelPct / 100) * TANK_H);
}

// ── Sub-componente: tanque individual ────────────────────────
function WaterTank({
  x, levelPct, groupId, tankIdx,
}: {
  x: number;
  levelPct: number;
  groupId: 1 | 2;
  tankIdx: number;
}) {
  const ty = TANK_Y;
  const tw = TANK_W;
  const th = TANK_H;
  const wy = waterY(levelPct);
  const wh = ty + th - wy;
  const cx = x + tw / 2;
  const clipId = `clip-g${groupId}-t${tankIdx}`;

  return (
    <g>
      <title>Caixa {tankIdx + 1} — {levelPct}% de nível — 10.000 L</title>

      {/* Corpo do tanque */}
      <rect x={x} y={ty} width={tw} height={th} rx={5}
        fill="hsl(220 45% 28%)" stroke="hsl(220 30% 45%)" strokeWidth={1.5} />

      {/* Tampa */}
      <rect x={x + 4} y={ty - 10} width={tw - 8} height={12} rx={3}
        fill="hsl(220 35% 22%)" />

      {/* Clip para a água */}
      <clipPath id={clipId}>
        <rect x={x} y={ty} width={tw} height={th} rx={5} />
      </clipPath>

      <g clipPath={`url(#${clipId})`}>
        {/* Coluna de água */}
        <rect x={x} y={wy} width={tw} height={wh} fill="url(#water-fill)" />

        {/* Onda 1 (mais rápida) */}
        <path
          className="schema-tank-wave"
          d={`M ${x - 60} ${wy} Q ${x - 15} ${wy - 8} ${cx} ${wy} T ${cx + 90} ${wy} T ${cx + 180} ${wy} T ${cx + 270} ${wy} L ${x + 270} ${ty + th} L ${x - 60} ${ty + th} Z`}
          fill="hsl(var(--primary-glow))"
          opacity="0.45"
        />
        {/* Onda 2 (mais lenta, reversa) */}
        <path
          className="schema-tank-wave-2"
          d={`M ${x - 60} ${wy + 5} Q ${x - 15} ${wy - 2} ${cx} ${wy + 5} T ${cx + 90} ${wy + 5} T ${cx + 180} ${wy + 5} T ${cx + 270} ${wy + 5} L ${x + 270} ${ty + th} L ${x - 60} ${ty + th} Z`}
          fill="hsl(var(--primary-glow))"
          opacity="0.25"
        />
      </g>

      {/* % nível dentro d'água */}
      <text
        x={cx} y={wy + (wh > 40 ? wh / 2 + 6 : wh + 16)}
        textAnchor="middle"
        fontSize={wh > 50 ? 15 : 11}
        fontWeight="700"
        fill="white"
        fontFamily="Inter, sans-serif"
        opacity="0.92"
      >
        {levelPct}%
      </text>

      {/* Capacity label no ar (acima da água) */}
      {wy - ty > 20 && (
        <text x={cx} y={ty + (wy - ty) / 2 + 5}
          textAnchor="middle" fontSize={9} fill="hsl(210 20% 75%)"
          fontFamily="Inter, sans-serif">
          10k L
        </text>
      )}
    </g>
  );
}

// ── Sub-componente: reservatório de recalque (não monitorado) ─
function ContextReservoir({ x, label }: { x: number; label: string }) {
  const y = 337;
  const w = 200;
  const h = 142;
  const cx = x + w / 2;

  return (
    <g>
      <title>Reservatório de recalque — 40.000 L. Contexto hidráulico — sem sensor nesta etapa (POC).</title>

      {/* Corpo */}
      <rect x={x} y={y} width={w} height={h} rx={6}
        fill="hsl(215 12% 78%)" stroke="hsl(215 10% 68%)" strokeWidth={1.5} />

      {/* Tampa discreta */}
      <rect x={x + 6} y={y - 8} width={w - 12} height={10} rx={3}
        fill="hsl(215 10% 70%)" />

      {/* Linha decorativa (não é onda — sem sensor) */}
      <line x1={x + 16} y1={y + h - 28} x2={x + w - 16} y2={y + h - 28}
        stroke="hsl(215 10% 65%)" strokeWidth={1} strokeDasharray="4 4" />

      {/* Capacity */}
      <text x={cx} y={y + h / 2 - 8} textAnchor="middle"
        fontSize={18} fontWeight="700" fill="hsl(215 10% 52%)"
        fontFamily="Inter, sans-serif">
        40.000 L
      </text>

      {/* Nome */}
      <text x={cx} y={y + h / 2 + 14} textAnchor="middle"
        fontSize={11} fill="hsl(215 10% 55%)"
        fontFamily="Inter, sans-serif">
        {label}
      </text>

      {/* Badge "Sem sensor" */}
      <rect x={cx - 52} y={y + h - 24} width={104} height={18} rx={9}
        fill="hsl(215 10% 68%)" />
      <text x={cx} y={y + h - 12} textAnchor="middle"
        fontSize={9} fontWeight="600" fill="hsl(215 10% 35%)"
        fontFamily="Inter, sans-serif" letterSpacing="0.04em">
        SEM SENSOR
      </text>
    </g>
  );
}

// ── Componente principal ──────────────────────────────────────
export function HospitalHydraulicScheme({ data }: Props) {
  const g1 = data.tankGroups[0];
  const g2 = data.tankGroups[1];
  const g1cx = 20 + 495 / 2;   // 267
  const g2cx = 685 + 495 / 2;  // 932

  return (
    <div className="rounded-3xl border border-border bg-card shadow-soft overflow-hidden">
      {/* Header do card */}
      <div className="flex flex-wrap items-baseline justify-between gap-4 px-6 pt-6 pb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Esquema hidráulico
          </p>
          <h3 className="mt-1 text-xl font-semibold text-foreground">
            Topologia da instalação
          </h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Medição nas caixas superiores · distribuição por gravidade
          </p>
        </div>

        {/* Legenda */}
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          <span className="inline-flex items-center gap-1.5 text-primary font-medium">
            <span className="h-2.5 w-2.5 rounded-full bg-primary" />
            Monitorado (sensor)
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/40" />
            Não monitorado nesta etapa
          </span>
        </div>
      </div>

      {/* Diagrama SVG */}
      <div className="w-full overflow-x-auto px-4 pb-6">
        <svg
          viewBox="0 0 1200 648"
          className="w-full h-auto min-w-[820px]"
          aria-label="Esquema hidráulico Hospital Santa Ana"
        >
          <defs>
            {/* Gradiente da água */}
            <linearGradient id="water-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.9" />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="1" />
            </linearGradient>

            {/* Gradiente cano (metálico) */}
            <linearGradient id="pipe-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="hsl(210 15% 82%)" />
              <stop offset="50%"  stopColor="hsl(210 12% 93%)" />
              <stop offset="100%" stopColor="hsl(210 18% 72%)" />
            </linearGradient>

            {/* Gradiente cano azul (gravidade) */}
            <linearGradient id="pipe-blue" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%"   stopColor="hsl(var(--primary-glow))" stopOpacity="0.8" />
              <stop offset="100%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.5" />
            </linearGradient>

            {/* Gradiente display do hidrômetro */}
            <radialGradient id="meter-screen" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor="hsl(195 80% 70%)" />
              <stop offset="100%" stopColor="hsl(210 60% 35%)" />
            </radialGradient>

            {/* Glow para grupos monitorados */}
            <filter id="group-glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" />
            </filter>
          </defs>

          {/* ======================================================
              FUNDO geral
          ====================================================== */}
          <rect x="0" y="0" width="1200" height="648" fill="hsl(210 30% 97%)" rx="0" />

          {/* Linha indicadora do "nível do solo" */}
          <line x1="0" y1="496" x2="1200" y2="496"
            stroke="hsl(var(--border))" strokeWidth="1" strokeDasharray="6 10" />
          <text x="8" y="491" fontSize="9" fill="hsl(var(--muted-foreground))"
            fontFamily="Inter, sans-serif" letterSpacing="0.06em">
            nível do solo
          </text>

          {/* ======================================================
              TUBULAÇÕES DE GRAVIDADE (azuis, nas bordas)
              Grupo 1 → ↓ → Prédio (esquerda)
              Grupo 2 → ↓ → Prédio (direita)
          ====================================================== */}

          {/* Cano lateral esquerdo (gravidade G1) */}
          <path d={`M ${g1cx} 280 L 36 280 L 36 574`}
            stroke="url(#pipe-grad)" strokeWidth={12}
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <path d={`M ${g1cx} 280 L 36 280 L 36 574`}
            stroke="hsl(var(--primary-glow))" strokeWidth={2.5}
            fill="none" strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray="8 10" className="schema-flow" />
          {/* Seta indicando gravidade (baixo) */}
          <polygon points={`36,578 30,565 42,565`}
            fill="hsl(var(--primary-glow))" opacity="0.8" />

          {/* Cano lateral direito (gravidade G2) */}
          <path d={`M ${g2cx} 280 L 1164 280 L 1164 574`}
            stroke="url(#pipe-grad)" strokeWidth={12}
            fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <path d={`M ${g2cx} 280 L 1164 280 L 1164 574`}
            stroke="hsl(var(--primary-glow))" strokeWidth={2.5}
            fill="none" strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray="8 10" className="schema-flow" />
          <polygon points={`1164,578 1158,565 1170,565`}
            fill="hsl(var(--primary-glow))" opacity="0.8" />

          {/* Etiqueta "Distribuição por gravidade" */}
          <text x="600" y="292" textAnchor="middle" fontSize="11" fontWeight="600"
            fill="hsl(var(--primary))" fontFamily="Inter, sans-serif">
            ↓ Distribuição por gravidade ↓
          </text>

          {/* ======================================================
              TUBULAÇÕES DE RECALQUE (canos cinza, dos cisternões → caixas)
          ====================================================== */}

          {/* Cano recalque G1 (cinza dashed — não monitorado) */}
          <line x1={g1cx} y1="281" x2={g1cx} y2="335"
            stroke="hsl(215 10% 68%)" strokeWidth={10} strokeLinecap="round" />
          <line x1={g1cx} y1="281" x2={g1cx} y2="335"
            stroke="hsl(215 10% 82%)" strokeWidth={2}
            strokeDasharray="4 5" />
          {/* Seta recalque (para cima) */}
          <polygon points={`${g1cx},278 ${g1cx - 6},288 ${g1cx + 6},288`}
            fill="hsl(215 10% 60%)" />
          {/* Label recalque */}
          <text x={g1cx + 14} y="310" fontSize="10" fill="hsl(215 10% 52%)"
            fontFamily="Inter, sans-serif" fontStyle="italic">
            ↑ recalque
          </text>

          {/* Cano recalque G2 */}
          <line x1={g2cx} y1="281" x2={g2cx} y2="335"
            stroke="hsl(215 10% 68%)" strokeWidth={10} strokeLinecap="round" />
          <line x1={g2cx} y1="281" x2={g2cx} y2="335"
            stroke="hsl(215 10% 82%)" strokeWidth={2}
            strokeDasharray="4 5" />
          <polygon points={`${g2cx},278 ${g2cx - 6},288 ${g2cx + 6},288`}
            fill="hsl(215 10% 60%)" />
          <text x={g2cx + 14} y="310" fontSize="10" fill="hsl(215 10% 52%)"
            fontFamily="Inter, sans-serif" fontStyle="italic">
            ↑ recalque
          </text>

          {/* ======================================================
              TUBULAÇÃO HORIZONTAL DE ALIMENTAÇÃO (SABESP → cisternões)
          ====================================================== */}

          {/* Cano horizontal principal */}
          <path d="M 112 382 L 167 382" stroke="url(#pipe-grad)" strokeWidth={14}
            strokeLinecap="round" fill="none" />
          <path d="M 112 382 L 167 382" stroke="hsl(var(--primary-glow))"
            strokeWidth={3} strokeDasharray="8 10" fill="none"
            className="schema-flow" />

          {/* Cano entre recalques */}
          <path d="M 367 382 L 832 382" stroke="url(#pipe-grad)" strokeWidth={14}
            strokeLinecap="round" fill="none" />
          <path d="M 367 382 L 832 382" stroke="hsl(var(--primary-glow))"
            strokeWidth={3} strokeDasharray="8 10" fill="none"
            className="schema-flow" />

          {/* Cano entrando em Rec1 (top, vertical) */}
          <line x1={g1cx} y1="337" x2={g1cx} y2="382"
            stroke="url(#pipe-grad)" strokeWidth={10} strokeLinecap="round" />

          {/* Cano entrando em Rec2 (top, vertical) */}
          <line x1={g2cx} y1="337" x2={g2cx} y2="382"
            stroke="url(#pipe-grad)" strokeWidth={10} strokeLinecap="round" />

          {/* ======================================================
              GRUPO 1 — 4 caixas de 10.000 L (MONITORADO)
          ====================================================== */}

          {/* Fundo azul do grupo */}
          <rect x="20" y="16" width="495" height="264" rx="10"
            fill="hsl(215 60% 96%)" stroke="hsl(215 55% 82%)" strokeWidth="1.5" />

          {/* Header Grupo 1 */}
          <text x={g1cx} y="36" textAnchor="middle" fontSize="12" fontWeight="700"
            fill="hsl(var(--primary))" fontFamily="Inter, sans-serif"
            letterSpacing="0.04em">
            GRUPO 1 — 4×10.000 L
          </text>

          {/* Badge "Monitorado" G1 */}
          <rect x={g1cx + 65} y="22" width="80" height="16" rx="8"
            fill="hsl(140 60% 92%)" stroke="hsl(140 50% 70%)" strokeWidth="1" />
          <circle cx={g1cx + 73} cy="30" r="3" fill="hsl(140 60% 45%)" />
          <text x={g1cx + 79} y="34" fontSize="8" fontWeight="600"
            fill="hsl(140 60% 35%)" fontFamily="Inter, sans-serif">
            Monitorado
          </text>

          {/* Sensor LV — G1 */}
          <circle cx={g1cx - 70} cy="30" r="5"
            fill="hsl(var(--accent))" stroke="hsl(var(--accent))" strokeWidth="1" />
          <line x1={g1cx - 70} y1="35" x2={g1cx - 70} y2={waterY(g1.levelPct)}
            stroke="hsl(var(--accent))" strokeWidth="1.5" strokeDasharray="3 3" />
          <text x={g1cx - 80} y="28" textAnchor="end" fontSize="10" fontWeight="700"
            fill="hsl(var(--foreground))" fontFamily="Inter, sans-serif">
            Sensor LV
          </text>
          <text x={g1cx - 80} y="40" textAnchor="end" fontSize="9"
            fill="hsl(var(--muted-foreground))" fontFamily="Inter, sans-serif">
            nível ultrassônico
          </text>

          {/* Tanques G1 */}
          {G1_TANKS.map((tx, i) => (
            <WaterTank key={`g1-${i}`} x={tx} levelPct={g1.levelPct} groupId={1} tankIdx={i} />
          ))}

          {/* Nível médio do grupo */}
          <text x={g1cx} y="256" textAnchor="middle" fontSize="11" fontWeight="600"
            fill="hsl(var(--primary))" fontFamily="Inter, sans-serif">
            Nível médio: {g1.levelPct}% · Autonomia: ~{g1.estimatedAutonomyHours}h
          </text>

          {/* Status badge G1 */}
          <rect x={g1cx - 38} y="260" width="76" height="16" rx="8"
            fill="hsl(140 60% 92%)" stroke="hsl(140 50% 70%)" strokeWidth="1" />
          <text x={g1cx} y="272" textAnchor="middle" fontSize="9" fontWeight="700"
            fill="hsl(140 55% 35%)" fontFamily="Inter, sans-serif"
            letterSpacing="0.06em">
            OPERAÇÃO NORMAL
          </text>

          {/* ======================================================
              GRUPO 2 — 4 caixas de 10.000 L (MONITORADO)
          ====================================================== */}

          {/* Fundo azul do grupo */}
          <rect x="685" y="16" width="495" height="264" rx="10"
            fill="hsl(215 60% 96%)" stroke="hsl(215 55% 82%)" strokeWidth="1.5" />

          {/* Header Grupo 2 */}
          <text x={g2cx} y="36" textAnchor="middle" fontSize="12" fontWeight="700"
            fill="hsl(var(--primary))" fontFamily="Inter, sans-serif"
            letterSpacing="0.04em">
            GRUPO 2 — 4×10.000 L
          </text>

          {/* Badge "Monitorado" G2 */}
          <rect x={g2cx + 65} y="22" width="80" height="16" rx="8"
            fill="hsl(140 60% 92%)" stroke="hsl(140 50% 70%)" strokeWidth="1" />
          <circle cx={g2cx + 73} cy="30" r="3" fill="hsl(140 60% 45%)" />
          <text x={g2cx + 79} y="34" fontSize="8" fontWeight="600"
            fill="hsl(140 60% 35%)" fontFamily="Inter, sans-serif">
            Monitorado
          </text>

          {/* Sensor LV — G2 */}
          <circle cx={g2cx + 70} cy="30" r="5"
            fill="hsl(var(--accent))" stroke="hsl(var(--accent))" strokeWidth="1" />
          <line x1={g2cx + 70} y1="35" x2={g2cx + 70} y2={waterY(g2.levelPct)}
            stroke="hsl(var(--accent))" strokeWidth="1.5" strokeDasharray="3 3" />
          <text x={g2cx + 82} y="28" fontSize="10" fontWeight="700"
            fill="hsl(var(--foreground))" fontFamily="Inter, sans-serif">
            Sensor LV
          </text>
          <text x={g2cx + 82} y="40" fontSize="9"
            fill="hsl(var(--muted-foreground))" fontFamily="Inter, sans-serif">
            nível ultrassônico
          </text>

          {/* Tanques G2 */}
          {G2_TANKS.map((tx, i) => (
            <WaterTank key={`g2-${i}`} x={tx} levelPct={g2.levelPct} groupId={2} tankIdx={i} />
          ))}

          {/* Nível médio Grupo 2 */}
          <text x={g2cx} y="256" textAnchor="middle" fontSize="11" fontWeight="600"
            fill="hsl(var(--primary))" fontFamily="Inter, sans-serif">
            Nível médio: {g2.levelPct}% · Autonomia: ~{g2.estimatedAutonomyHours}h
          </text>

          {/* Status badge G2 — ATENÇÃO */}
          <rect x={g2cx - 32} y="260" width="64" height="16" rx="8"
            fill="hsl(42 80% 92%)" stroke="hsl(42 70% 65%)" strokeWidth="1" />
          <text x={g2cx} y="272" textAnchor="middle" fontSize="9" fontWeight="700"
            fill="hsl(32 80% 38%)" fontFamily="Inter, sans-serif"
            letterSpacing="0.06em">
            ATENÇÃO
          </text>

          {/* ======================================================
              RESERVATÓRIOS DE RECALQUE (não monitorados)
          ====================================================== */}

          <ContextReservoir x={167} label="Recalque 1" />
          <ContextReservoir x={832} label="Recalque 2" />

          {/* Labels abaixo dos cisternões */}
          <text x={267} y="500" textAnchor="middle" fontSize="11" fontWeight="600"
            fill="hsl(215 10% 45%)" fontFamily="Inter, sans-serif">
            Reservatório de recalque — 40.000 L
          </text>
          <text x={267} y="514" textAnchor="middle" fontSize="9"
            fill="hsl(215 10% 55%)" fontFamily="Inter, sans-serif">
            Não monitorado nesta etapa
          </text>

          <text x={932} y="500" textAnchor="middle" fontSize="11" fontWeight="600"
            fill="hsl(215 10% 45%)" fontFamily="Inter, sans-serif">
            Reservatório de recalque — 40.000 L
          </text>
          <text x={932} y="514" textAnchor="middle" fontSize="9"
            fill="hsl(215 10% 55%)" fontFamily="Inter, sans-serif">
            Não monitorado nesta etapa
          </text>

          {/* ======================================================
              SABESP — ENTRADA
          ====================================================== */}
          <g>
            <rect x="18" y="354" width="90" height="58" rx="6"
              fill="hsl(220 65% 28%)" />
            <text x="63" y="381" textAnchor="middle" fontSize="13" fontWeight="800"
              fill="white" fontFamily="Inter, sans-serif">
              SABESP
            </text>
            <text x="63" y="396" textAnchor="middle" fontSize="10"
              fill="hsl(210 30% 85%)" fontFamily="Inter, sans-serif">
              entrada
            </text>
            {/* Seta saindo para a direita */}
            <polygon points="108,379 108,393 118,386" fill="hsl(220 65% 28%)" />
          </g>
          <text x="63" y="428" textAnchor="middle" fontSize="9"
            fill="hsl(var(--muted-foreground))" fontFamily="Inter, sans-serif">
            Entrada SABESP
          </text>

          {/* ======================================================
              HIDRÔMETRO PRINCIPAL
          ====================================================== */}
          <g transform="translate(120, 352)">
            <rect x="0" y="0" width="85" height="68" rx="7"
              fill="hsl(220 25% 92%)" stroke="hsl(220 20% 60%)" strokeWidth="1.5" />
            {/* Display digital */}
            <rect x="8" y="8" width="69" height="28" rx="3" fill="url(#meter-screen)" />
            <text x="42" y="28" textAnchor="middle" fontSize="14" fontWeight="700"
              fill="white" fontFamily="ui-monospace, monospace">
              2,6
            </text>
            <text x="42" y="40" textAnchor="middle" fontSize="8"
              fill="hsl(210 30% 85%)" fontFamily="ui-monospace, monospace">
              m³/h
            </text>
            {/* LEDs status */}
            <circle cx="20" cy="56" r="3.5" fill="hsl(140 60% 50%)" />
            <circle cx="42" cy="56" r="3.5" fill="hsl(45 90% 55%)" />
            <circle cx="64" cy="56" r="3.5" fill="hsl(0 70% 55%)" />
          </g>
          <text x="162" y="432" textAnchor="middle" fontSize="10" fontWeight="600"
            fill="hsl(var(--foreground))" fontFamily="Inter, sans-serif">
            Hidrômetro principal
          </text>

          {/* ======================================================
              PRÉDIO — HOSPITAL SANTA ANA (base)
          ====================================================== */}
          <rect x="20" y="577" width="1160" height="52" rx="8"
            fill="hsl(220 30% 22%)" />

          {/* Janelas decorativas no prédio */}
          {Array.from({ length: 14 }, (_, i) => (
            <rect key={i}
              x={48 + i * 82} y="585" width="54" height="30" rx="2"
              fill="hsl(210 50% 35%)"
              opacity={i % 3 === 0 ? 0.9 : 0.5}
            />
          ))}

          {/* Nome do prédio */}
          <text x="600" y="608" textAnchor="middle" fontSize="13" fontWeight="700"
            fill="hsl(210 40% 85%)" fontFamily="Inter, sans-serif"
            letterSpacing="0.04em">
            Hospital Santa Ana · Santana de Parnaíba
          </text>

          {/* ======================================================
              ÍCONE DE POC — lembrete discreto
          ====================================================== */}
          <text x="600" y="640" textAnchor="middle" fontSize="9"
            fill="hsl(var(--muted-foreground))" fontFamily="Inter, sans-serif"
            fontStyle="italic">
            POC — dados simulados · sem integração com sensores reais nesta etapa
          </text>

        </svg>
      </div>
    </div>
  );
}
