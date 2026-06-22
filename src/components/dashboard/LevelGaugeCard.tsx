import { useEffect, useRef, useState } from 'react';
import { ReservoirGauge } from './ReservoirGauge';
import { cn } from '../../lib/cn';
import type { DashDevice, SeriesPoint } from '../../types/telemetry';

// ── helpers ──────────────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1100) {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>(0);
  useEffect(() => {
    const start = performance.now();
    function tick(now: number) {
      const t = Math.min(1, (now - start) / duration);
      const ease = 1 - Math.pow(1 - t, 3);
      setValue(target * ease);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);
  return value;
}

function fmtDt(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}

function fmtLiters(l: number | null | undefined): string {
  if (l == null) return '—';
  return `${Math.round(l).toLocaleString('pt-BR')} L`;
}

function fmtAltura(nivel: number | null | undefined, ref: number): string {
  if (nivel == null) return '—';
  return `${nivel.toFixed(3)} m / ${ref.toFixed(3)} m`;
}

// ── consumo derivado de flow_consumo_lph ─────────────────────────────────────

interface Consumption {
  taxaAtual: number | null;    // L/h
  taxaMedia: number | null;    // L/h
  autonomiaDias: number | null;
  tendencia: 'consumindo' | 'enchendo' | 'estável';
}

function deriveConsumption(series: SeriesPoint[], volumeL: number | null | undefined): Consumption {
  const neutral: Consumption = { taxaAtual: null, taxaMedia: null, autonomiaDias: null, tendencia: 'estável' };
  if (series.length === 0) return neutral;

  const taxaAtual = series[series.length - 1].v;
  const taxaMedia = series.reduce((s, p) => s + p.v, 0) / series.length;

  const autonomiaDias =
    taxaAtual > 0.1 && volumeL != null && volumeL > 0
      ? volumeL / taxaAtual / 24
      : null;

  // flow_consumo_lph é consumo retificado (≥0): 0 = estável/enchendo
  const tendencia: Consumption['tendencia'] =
    taxaAtual > 0.1 ? 'consumindo' : 'estável';

  return { taxaAtual, taxaMedia, autonomiaDias, tendencia };
}

function fmtLph(r: number | null): string {
  if (r == null) return '—';
  if (r < 0.1) return '0 L/h';
  return `${Math.round(r).toLocaleString('pt-BR')} L/h`;
}

function fmtDias(d: number | null): string {
  if (d == null) return '∞';
  if (d > 365) return '>1 ano';
  return `${d.toFixed(1)} dias`;
}

// ── estado ────────────────────────────────────────────────────────────────────

type EstadoKey = 'Confortável' | 'Moderado' | 'Alto' | 'Crítico' | 'Sem leitura';

function getEstado(pct: number | null | undefined): EstadoKey {
  if (pct == null) return 'Sem leitura';
  if (pct <= 10) return 'Crítico';
  if (pct <= 15) return 'Alto';
  if (pct <= 20) return 'Moderado';
  return 'Confortável';
}

const ESTADO_TONE: Record<EstadoKey, string> = {
  'Confortável': 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  'Moderado':    'bg-blue-500/10 text-blue-600 border-blue-500/30',
  'Alto':        'bg-accent/15 text-accent-foreground border-accent/40',
  'Crítico':     'bg-destructive/10 text-destructive border-destructive/40',
  'Sem leitura': 'bg-muted text-muted-foreground border-border',
};

// ── chips de status ───────────────────────────────────────────────────────────

interface ChipDef {
  label: string;
  tone: 'green' | 'blue' | 'amber' | 'red' | 'neutral';
}

function buildChips(estado: EstadoKey, cons: Consumption): ChipDef[] {
  const chips: ChipDef[] = [];

  // Nível
  if (estado === 'Confortável') chips.push({ label: 'Nível: confortável', tone: 'green' });
  else if (estado === 'Moderado') chips.push({ label: 'Nível: moderado', tone: 'blue' });
  else if (estado === 'Alto') chips.push({ label: 'Nível: alto', tone: 'amber' });
  else if (estado === 'Crítico') chips.push({ label: 'Nível: crítico', tone: 'red' });
  else chips.push({ label: 'Sem leitura', tone: 'neutral' });

  // Autonomia
  if (cons.autonomiaDias == null) {
    chips.push({ label: 'Autonomia: estável', tone: 'green' });
  } else if (cons.autonomiaDias > 7) {
    chips.push({ label: 'Autonomia: confortável', tone: 'green' });
  } else if (cons.autonomiaDias > 2) {
    chips.push({ label: 'Autonomia: atenção', tone: 'amber' });
  } else {
    chips.push({ label: 'Autonomia: crítico', tone: 'red' });
  }

  // Tendência
  if (cons.tendencia === 'consumindo') {
    chips.push({ label: 'Tendência: consumindo', tone: 'neutral' });
  } else {
    chips.push({ label: 'Grupo: estável', tone: 'green' });
  }

  return chips;
}

const CHIP_CLASS: Record<ChipDef['tone'], string> = {
  green:   'bg-emerald-500/10 border-emerald-500/25 text-emerald-700',
  blue:    'bg-blue-500/10 border-blue-500/25 text-blue-700',
  amber:   'bg-amber-500/10 border-amber-500/25 text-amber-700',
  red:     'bg-destructive/10 border-destructive/30 text-destructive',
  neutral: 'bg-secondary border-border text-muted-foreground',
};

// ── sub-components ────────────────────────────────────────────────────────────

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-3">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground leading-tight">{label}</p>
      <p className="mt-1.5 text-sm font-bold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

function StatusChip({ label, tone }: ChipDef) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium',
      CHIP_CLASS[tone],
    )}>
      {label}
    </span>
  );
}

// ── principal ─────────────────────────────────────────────────────────────────

export interface LevelGaugeCardProps {
  device: DashDevice;
  groupIndex: number;
}

// Altura útil de referência padrão (Fortlev 10.000 L) — usado se a API não retornar
const HEIGHT_REF_DEFAULT = 1.648;

export function LevelGaugeCard({ device, groupIndex }: LevelGaugeCardProps) {
  const pct     = device.latest.level_pct ?? 0;
  const animated = useCountUp(pct);
  const estado  = getEstado(device.latest.level_pct);

  const flowSeries: SeriesPoint[] = device.series?.['flow_consumo_lph'] ?? [];
  const cons = deriveConsumption(flowSeries, device.latest.volume_l);
  const chips = buildChips(estado, cons);

  const nivel = device.latest.nivel_m ?? device.latest.level_m;
  const heightRef = HEIGHT_REF_DEFAULT;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Nível atual</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">
            Grupo {groupIndex + 1} · Reservatórios
          </h3>
        </div>
        <p className="text-[11px] text-muted-foreground text-right">
          Última leitura:{' '}
          <span className="text-foreground tabular-nums">{fmtDt(device.last_seen_utc)}</span>
        </p>
      </div>

      {/* Body: gauge + análise */}
      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-6 items-center">
        {/* Esquerda: gauge + % + estado */}
        <div className="flex items-center gap-4">
          <ReservoirGauge level={pct} />
          <div>
            <p className="text-4xl font-bold tabular-nums text-foreground">
              {device.latest.level_pct == null ? '—' : animated.toFixed(1)}
              <span className="text-xl font-medium text-muted-foreground">%</span>
            </p>
            <span className={cn(
              'mt-2 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider',
              ESTADO_TONE[estado],
            )}>
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              Estado: {estado}
            </span>
          </div>
        </div>

        {/* Direita: análise de consumo */}
        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-foreground">Análise de Consumo</p>
            <p className="text-[11px] text-muted-foreground">Indicadores de desempenho</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <Mini label="Autonomia"             value={fmtDias(cons.autonomiaDias)} />
            <Mini label="Consumo médio (janela)" value={fmtLph(cons.taxaMedia)} />
            <Mini label="Consumo atual"          value={fmtLph(cons.taxaAtual)} />
            <Mini label="Volume (grupo)"         value={fmtLiters(device.latest.volume_l)} />
            <Mini label="Faltante (grupo)"       value={fmtLiters(device.latest.faltante_l)} />
            <Mini label="Altura"                 value={fmtAltura(nivel, heightRef)} />
          </div>
          <div className="flex flex-wrap gap-2">
            {chips.map((c, i) => <StatusChip key={i} {...c} />)}
          </div>
        </div>
      </div>
    </div>
  );
}

export default LevelGaugeCard;
