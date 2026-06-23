import { useState } from 'react';
import { Switch } from '../ui/Switch';
import type { WindowKey, FilterMode, ConsumptionSummary } from '../../types/telemetry';
import { WINDOW_OPTIONS } from '../../constants/dashboard';
import { cn } from '../../lib/cn';
import { ConsumptionSummaryChip } from './ConsumptionSummaryChip';

interface FiltersBarProps {
  mode: FilterMode;
  onModeChange: (m: FilterMode) => void;
  windowKey: WindowKey;
  onWindowChange: (w: WindowKey) => void;
  // Chip de consumo — opcional; só renderiza quando onShiftChange estiver presente
  consumptionSummary?: ConsumptionSummary | null;
  shiftStart?: string;
  shiftEnd?: string;
  onShiftChange?: (start: string, end: string) => void;
}

function formatDateInputValue(date: Date) {
  return date.toISOString().slice(0, 10);
}

export function FiltersBar(p: FiltersBarProps) {
  const [periodDefaults] = useState(() => {
    const end = new Date();
    const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);

    return {
      start: formatDateInputValue(start),
      end: formatDateInputValue(end),
    };
  });

  return (
    <div className="relative z-20 rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-4">
        Filtros de visualização
      </p>

      <div className="flex flex-wrap items-end gap-4">
        {/* Switch janela/período */}
        <div>
          <p className="text-xs text-muted-foreground mb-2">Modo de filtro</p>
          <div className="flex items-center gap-3 rounded-full border border-border px-3 py-1.5">
            <span className={p.mode === 'janela' ? 'text-foreground font-medium text-sm' : 'text-muted-foreground text-sm'}>
              Janela
            </span>
            <Switch
              checked={p.mode === 'periodo'}
              onCheckedChange={(c) => p.onModeChange(c ? 'periodo' : 'janela')}
            />
            <span className={p.mode === 'periodo' ? 'text-foreground font-medium text-sm' : 'text-muted-foreground text-sm'}>
              Período
            </span>
          </div>
        </div>

        {/* Botões de janela */}
        {p.mode === 'janela' ? (
          <div>
            <p className="text-xs text-muted-foreground mb-2">Janela</p>
            <div className="inline-flex rounded-xl border border-border bg-secondary/40 p-1">
              {WINDOW_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => p.onWindowChange(opt.value)}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
                    p.windowKey === opt.value
                      ? 'bg-card text-foreground shadow-soft'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex gap-3">
            <div>
              <p className="text-xs text-muted-foreground mb-2">Início</p>
              <input
                type="date"
                className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                defaultValue={periodDefaults.start}
              />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-2">Fim</p>
              <input
                type="date"
                className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                defaultValue={periodDefaults.end}
              />
            </div>
          </div>
        )}

        <div className="flex-1" />

        {/* Chip de consumo acumulado — apenas no Dashboard */}
        {p.onShiftChange && (
          <ConsumptionSummaryChip
            summary={p.consumptionSummary}
            shiftStart={p.shiftStart ?? '07:00'}
            shiftEnd={p.shiftEnd ?? '19:00'}
            onApply={p.onShiftChange}
          />
        )}
      </div>
    </div>
  );
}

export default FiltersBar;
