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

// Altura real da coluna de água medida pelo sensor (nivel_m), formato pt-BR.
function fmtAltura(nivel: number | null | undefined): string {
  if (nivel == null) return '—';
  return `${nivel.toFixed(3).replace('.', ',')} m`;
}

// ── consumo derivado de flow_consumo_lph ─────────────────────────────────────

interface Consumption {
  taxaAtual: number | null;    // L/h (último ponto)
  taxaMedia: number | null;    // L/h (média da janela)
  autonomiaDias: number | null;
  tendencia: 'consumindo' | 'enchendo' | 'estável';
}

function deriveConsumption(series: SeriesPoint[], volumeL: number | null | undefined): Consumption {
  const neutral: Consumption = { taxaAtual: null, taxaMedia: null, autonomiaDias: null, tendencia: 'estável' };
  if (series.length === 0) return neutral;

  const taxaAtual = series[series.length - 1].v;
  const taxaMedia = series.reduce((s, p) => s + p.v, 0) / series.length;

  // Autonomia usa o consumo MÉDIO da janela (mais estável que o ponto instantâneo).
  const autonomiaDias =
    taxaMedia > 0.1 && volumeL != null && volumeL > 0
      ? volumeL / taxaMedia / 24
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
  if (d == null) return '0 dias';
  if (d > 365) return '>1 ano';
  return `${d.toFixed(1).replace('.', ',')} dias`;
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

type StatTone = 'normal' | 'amber' | 'red';

function autonomiaTone(d: number | null): StatTone {
  if (d == null) return 'normal';
  if (d <= 2) return 'red';
  if (d <= 7) return 'amber';
  return 'normal';
}

const STAT_TONE: Record<StatTone, string> = {
  normal: 'text-foreground',
  amber:  'text-amber-600',
  red:    'text-destructive',
};

// ── chips de status ───────────────────────────────────────────────────────────

interface ChipDef {
  label: string;
  tone: 'green' | 'blue' | 'amber' | 'red' | 'neutral';
}

function buildChips(estado: EstadoKey, cons: Consumption): ChipDef[] {
  const chips: ChipDef[] = [];

  // Nível (indicador de estado — único, sem badge duplicado)
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

function StatSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-medium mb-1">
        {title}
      </p>
      <div>{children}</div>
    </div>
  );
}

function StatRow({ label, value, tone = 'normal' }: { label: string; value: string; tone?: StatTone }) {
  return (
    <div className="flex items-baseline justify-between py-1">
      <span className="text-[13px] text-muted-foreground">{label}</span>
      <span className={cn('text-sm font-bold tabular-nums', STAT_TONE[tone])}>{value}</span>
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

export function LevelGaugeCard({ device, groupIndex }: LevelGaugeCardProps) {
  const pct      = device.latest.level_pct ?? 0;
  const animated = useCountUp(pct);
  const estado   = getEstado(device.latest.level_pct);

  const flowSeries: SeriesPoint[] = device.series?.['flow_consumo_lph'] ?? [];
  const cons  = deriveConsumption(flowSeries, device.latest.volume_l);
  const chips = buildChips(estado, cons);

  const nivel = device.latest.nivel_m ?? device.latest.level_m;

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

      {/* Body: gauge+chips | stat-list */}
      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-6 items-start">
        {/* Esquerda: gauge + % + altura + chips empilhados */}
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-4">
            <ReservoirGauge level={pct} />
            <div>
              <p className="text-4xl font-bold tabular-nums text-foreground leading-none">
                {device.latest.level_pct == null ? '—' : animated.toFixed(1)}
                <span className="text-xl font-medium text-muted-foreground">%</span>
              </p>
              <p className="mt-2 text-[11px] text-muted-foreground">
                Coluna de água:{' '}
                <span className="text-foreground font-semibold tabular-nums">{fmtAltura(nivel)}</span>
              </p>
            </div>
          </div>

          {/* Chips abaixo do desenho */}
          <div className="flex flex-col gap-1.5 items-start">
            {chips.map((c, i) => <StatusChip key={i} {...c} />)}
          </div>
        </div>

        {/* Direita: stat-list por seção semântica */}
        <div className="space-y-3">
          <StatSection title="Reservatório">
            <StatRow label="Volume (grupo)"   value={fmtLiters(device.latest.volume_l)} />
            <StatRow label="Faltante (grupo)" value={fmtLiters(device.latest.faltante_l)} />
          </StatSection>

          <div className="border-t border-border" />

          <StatSection title="Consumo">
            <StatRow label="Atual"          value={fmtLph(cons.taxaAtual)} />
            <StatRow label="Médio (janela)" value={fmtLph(cons.taxaMedia)} />
          </StatSection>

          <div className="border-t border-border" />

          <StatSection title="Operação">
            <StatRow
              label="Autonomia"
              value={fmtDias(cons.autonomiaDias)}
              tone={autonomiaTone(cons.autonomiaDias)}
            />
          </StatSection>
        </div>
      </div>
    </div>
  );
}

export default LevelGaugeCard;
