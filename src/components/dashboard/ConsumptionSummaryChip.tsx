import { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import { cn } from '../../lib/cn';
import { SHIFT_PRESETS } from '../../constants/dashboard';
import type { ConsumptionSummary, GroupConsumption } from '../../types/telemetry';

interface ConsumptionSummaryChipProps {
  summary?: ConsumptionSummary | null;
  shiftStart: string;
  shiftEnd: string;
  onApply: (start: string, end: string) => void;
  onOpenChange?: (open: boolean) => void;
}

function formatM3(value?: number) {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })} m³`;
}

function GroupStat({ group }: { group: GroupConsumption }) {
  return (
    <div className="min-w-0 text-left">
      <span className="text-[10px] font-semibold uppercase tracking-[0.16em] leading-none text-primary">
        {group.label}
      </span>
      <p className="mt-0.5 font-bold tabular-nums text-foreground text-[15px] leading-tight">
        {formatM3(group.m3)}
      </p>
    </div>
  );
}

export function ConsumptionSummaryChip({
  summary,
  shiftStart,
  shiftEnd,
  onApply,
  onOpenChange,
}: ConsumptionSummaryChipProps) {
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(shiftStart);
  const [draftEnd, setDraftEnd] = useState(shiftEnd);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const toMin = (hhmm: string) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
  const isWrap = shiftStart !== shiftEnd && toMin(shiftStart) > toMin(shiftEnd);
  const windowLabel = shiftStart === shiftEnd
    ? 'Dia inteiro'
    : isWrap
      ? `${shiftStart} (hoje) → ${shiftEnd} (amanhã)`
      : `${shiftStart} → ${shiftEnd}`;

  const groups = summary?.groups ?? [];

  return (
    <div ref={containerRef} className="relative w-full sm:w-auto">
      <button
        type="button"
        onClick={handleToggleOpen}
        aria-expanded={open}
        className={cn(
          'flex w-full items-center gap-3 rounded-xl border bg-card px-3.5 py-1.5 text-sm transition-colors sm:w-[28rem]',
          open
            ? 'border-primary/40 text-primary'
            : 'border-border text-foreground hover:border-primary/40 hover:text-primary',
        )}
      >
        {groups.length > 0 ? (
          <>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex items-stretch gap-3">
                {groups.flatMap((g, idx) => [
                  ...(idx > 0
                    ? [<span key={`sep-${idx}`} className="w-px self-stretch bg-border" aria-hidden="true" />]
                    : []),
                  <div key={g.index} className="min-w-0 flex-1">
                    <GroupStat group={g} />
                  </div>,
                ])}
              </div>
              <p className="text-center text-[10px] leading-none text-muted-foreground">{windowLabel}</p>
            </div>

            <Settings
              className={cn(
                'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground transition-transform duration-300',
                open && 'rotate-90 text-primary',
              )}
              aria-hidden="true"
            />
          </>
        ) : (
          <>
            <span className="flex-1 text-sm text-muted-foreground">{windowLabel}</span>
            <Settings
              className={cn(
                'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground transition-transform duration-300',
                open && 'rotate-90 text-primary',
              )}
              aria-hidden="true"
            />
          </>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-2xl border border-border bg-card p-4 shadow-soft animate-drop-in">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-1">
            Consumo
          </p>
          <h4 className="text-sm font-semibold text-foreground mb-1">
            Janela de horário analisada
          </h4>
          <p className="text-[11px] text-muted-foreground mb-4">
            Apenas o consumo dentro desta faixa de horário é somado — igual para os dois grupos.
          </p>

          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1">
              <p className="text-[11px] text-muted-foreground mb-1">Início</p>
              <input
                type="time"
                value={draftStart}
                onChange={(e) => setDraftStart(e.target.value)}
                className="w-full rounded-lg border border-border bg-secondary/40 px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary"
              />
            </div>
            <div className="flex-1">
              <p className="text-[11px] text-muted-foreground mb-1">Fim</p>
              <input
                type="time"
                value={draftEnd}
                onChange={(e) => setDraftEnd(e.target.value)}
                className="w-full rounded-lg border border-border bg-secondary/40 px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary"
              />
            </div>
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
