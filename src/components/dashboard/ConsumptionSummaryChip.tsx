import { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import { cn } from '../../lib/cn';
import { SHIFT_PRESETS } from '../../constants/dashboard';
import type { ConsumptionSummary } from '../../types/telemetry';
import { getShiftDisplayState } from '../../lib/shifts';

interface ConsumptionSummaryChipProps {
  summary?: ConsumptionSummary | null;
  shiftStart: string;
  shiftEnd: string;
  onApply: (start: string, end: string) => void;
  onOpenChange?: (open: boolean) => void;
  live?: boolean;
}

interface ShiftStatProps {
  tag: string;
  rangeText: string;
  value?: number;
  fill: number;
  active: boolean;
}

const TIME_PROGRESS_TITLE = 'Progresso do turno (tempo), não consumo';

function formatM3(value?: number) {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} m³`;
}

function clamp01(v: number) {
  return Math.min(1, Math.max(0, v));
}

function ShiftStat({ tag, rangeText, value, fill, active }: ShiftStatProps) {
  const fillPercent = Math.round(clamp01(fill) * 100);

  return (
    <div className="min-w-0 text-left">
      <div className="mb-1 flex min-h-4 items-center gap-1.5">
        <span className={cn(
          'text-[10px] font-semibold uppercase tracking-[0.16em]',
          active ? 'text-primary' : 'text-muted-foreground',
        )}>
          {tag}
        </span>
        {active && (
          <span className="rounded-full border border-primary/25 bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-primary">
            em curso
          </span>
        )}
      </div>

      <p className="truncate text-[10px] leading-none text-muted-foreground" title={rangeText}>
        {rangeText}
      </p>
      <p className="mt-0.5 font-bold tabular-nums text-foreground text-[15px] leading-snug">
        {formatM3(value)}
      </p>

      <div
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary"
        title={TIME_PROGRESS_TITLE}
        role="progressbar"
        aria-label={`${tag}: ${TIME_PROGRESS_TITLE}`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={fillPercent}
      >
        <div
          className={cn(
            'h-full rounded-full transition-[width] duration-700 ease-out',
            active ? 'bg-primary' : 'bg-muted-foreground/35',
          )}
          style={{ width: `${fillPercent}%` }}
        />
      </div>
    </div>
  );
}

export function ConsumptionSummaryChip({
  summary,
  shiftStart,
  shiftEnd,
  onApply,
  onOpenChange,
  live = true,
}: ConsumptionSummaryChipProps) {
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(shiftStart);
  const [draftEnd, setDraftEnd] = useState(shiftEnd);
  const [tick, setTick] = useState(() => Date.now());
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        onOpenChange?.(false);
        setDraftStart(shiftStart);
        setDraftEnd(shiftEnd);
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open, shiftStart, shiftEnd, onOpenChange]);

  function handleApply() {
    onApply(draftStart, draftEnd);
    setOpen(false);
    onOpenChange?.(false);
  }

  function handleCancel() {
    setDraftStart(shiftStart);
    setDraftEnd(shiftEnd);
    setOpen(false);
    onOpenChange?.(false);
  }

  function handleToggleOpen() {
    const next = !open;
    if (next) {
      setDraftStart(shiftStart);
      setDraftEnd(shiftEnd);
    }
    setOpen(next);
    onOpenChange?.(next);
  }

  const state = getShiftDisplayState({ now: tick, shiftStart, shiftEnd, live });

  const p2Start = draftEnd;
  const p2End = draftStart;

  return (
    <div ref={containerRef} className="relative w-full sm:w-auto">
      <button
        type="button"
        onClick={handleToggleOpen}
        aria-expanded={open}
        className={cn(
          'grid w-full grid-cols-[minmax(0,1fr)_1px_minmax(0,1fr)_auto] items-center gap-3 rounded-xl border bg-card px-3.5 py-2 text-sm transition-colors sm:w-[24rem]',
          open
            ? 'border-primary/40 text-primary'
            : 'border-border text-foreground hover:border-primary/40 hover:text-primary',
        )}
      >
        <ShiftStat
          tag={state.period1.label}
          rangeText={state.period1.rangeText}
          value={summary?.period_1_m3}
          fill={state.period1.fill}
          active={state.period1.isCurrent}
        />

        <span className="h-full min-h-12 w-px bg-border" aria-hidden="true" />

        <ShiftStat
          tag={state.period2.label}
          rangeText={state.period2.rangeText}
          value={summary?.period_2_m3}
          fill={state.period2.fill}
          active={state.period2.isCurrent}
        />

        <Settings
          className={cn(
            'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground transition-transform duration-300',
            open && 'rotate-90 text-primary',
          )}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-border bg-card p-4 shadow-soft animate-drop-in">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-1">
            Turnos
          </p>
          <h4 className="text-sm font-semibold text-foreground mb-1">
            Configurar períodos de consumo
          </h4>
          <p className="text-[11px] text-muted-foreground mb-4">
            Turnos que atravessam a meia-noite continuam em curso até o horário final configurado.
          </p>

          <div className="space-y-3 mb-4">
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <p className="text-[11px] text-muted-foreground mb-1">Início do 1º período</p>
                <input
                  type="time"
                  value={draftStart}
                  onChange={(e) => setDraftStart(e.target.value)}
                  className="w-full rounded-lg border border-border bg-secondary/40 px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
              <div className="flex-1">
                <p className="text-[11px] text-muted-foreground mb-1">Fim do 1º período</p>
                <input
                  type="time"
                  value={draftEnd}
                  onChange={(e) => setDraftEnd(e.target.value)}
                  className="w-full rounded-lg border border-border bg-secondary/40 px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
            </div>
          </div>

          <div className="rounded-xl bg-secondary/60 border border-border px-3 py-2 mb-4 space-y-1">
            <p className="text-[11px] text-muted-foreground">
              <span className="text-foreground font-medium">1º período:</span>{' '}
              {draftStart} às {draftEnd}
            </p>
            <p className="text-[11px] text-muted-foreground">
              <span className="text-foreground font-medium">2º período:</span>{' '}
              {p2Start} às {p2End}
            </p>
          </div>

          <div className="flex flex-wrap gap-1.5 mb-4">
            {SHIFT_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => { setDraftStart(p.start); setDraftEnd(p.end); }}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors',
                  draftStart === p.start && draftEnd === p.end
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground',
                )}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              className="flex-1 rounded-xl border border-border bg-secondary/40 px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleApply}
              className="flex-1 rounded-xl bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 transition-opacity"
            >
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ConsumptionSummaryChip;
