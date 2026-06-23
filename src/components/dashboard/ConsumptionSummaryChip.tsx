import { useEffect, useRef, useState } from 'react';
import { Settings } from 'lucide-react';
import { cn } from '../../lib/cn';
import { SHIFT_PRESETS } from '../../constants/dashboard';
import type { ConsumptionSummary } from '../../types/telemetry';

interface ConsumptionSummaryChipProps {
  summary?: ConsumptionSummary | null;
  shiftStart: string;
  shiftEnd: string;
  onApply: (start: string, end: string) => void;
}

function shiftLabel(start: string, end: string) {
  return `${start} – ${end}`;
}

export function ConsumptionSummaryChip({
  summary,
  shiftStart,
  shiftEnd,
  onApply,
}: ConsumptionSummaryChipProps) {
  const [open, setOpen] = useState(false);
  const [draftStart, setDraftStart] = useState(shiftStart);
  const [draftEnd, setDraftEnd] = useState(shiftEnd);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync drafts when props change (e.g. after apply)
  useEffect(() => {
    setDraftStart(shiftStart);
    setDraftEnd(shiftEnd);
  }, [shiftStart, shiftEnd]);

  // Click-outside closes popover
  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setDraftStart(shiftStart);
        setDraftEnd(shiftEnd);
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open, shiftStart, shiftEnd]);

  function handleApply() {
    onApply(draftStart, draftEnd);
    setOpen(false);
  }

  function handleCancel() {
    setDraftStart(shiftStart);
    setDraftEnd(shiftEnd);
    setOpen(false);
  }

  // Complementary period: end → start
  const p2Start = draftEnd;
  const p2End = draftStart;

  const totalLabel = summary != null
    ? `${summary.total_m3.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 2 })} m³`
    : '—';

  return (
    <div ref={containerRef} className="relative">
      {/* Chip button */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-2.5 rounded-xl border bg-card px-3.5 py-2 text-sm transition-colors',
          open
            ? 'border-primary/40 text-primary'
            : 'border-border text-foreground hover:border-primary/40 hover:text-primary',
        )}
      >
        <div className="text-left leading-tight">
          <p className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground font-medium">
            Consumo acumulado
          </p>
          <p className="font-bold tabular-nums text-foreground text-[15px] leading-snug">
            {totalLabel}
          </p>
          <p className="text-[10px] text-muted-foreground">
            {shiftLabel(shiftStart, shiftEnd)} / {shiftLabel(shiftEnd, shiftStart)}
          </p>
        </div>
        <Settings className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
      </button>

      {/* Popover */}
      {open && (
        <div className="absolute right-0 top-full mt-2 z-50 w-72 rounded-2xl border border-border bg-card p-4 shadow-soft">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-1">
            Turnos
          </p>
          <h4 className="text-sm font-semibold text-foreground mb-4">
            Configurar períodos de consumo
          </h4>

          {/* Time inputs */}
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

          {/* Preview */}
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

          {/* Presets */}
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

          {/* Actions */}
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
