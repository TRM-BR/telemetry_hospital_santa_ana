import { useState } from 'react';
import { Switch } from '../ui/Switch';
import type { WindowKey, FilterMode, ConsumptionSummary } from '../../types/telemetry';
import { WINDOW_OPTIONS } from '../../constants/dashboard';
import { cn } from '../../lib/cn';
import { ConsumptionSummaryChip } from './ConsumptionSummaryChip';
import { todaySaoPaulo } from '../../lib/shifts';


interface FiltersBarProps {
  mode: FilterMode;
  onModeChange: (m: FilterMode) => void;
  windowKey: WindowKey;
  onWindowChange: (w: WindowKey) => void;
  consumptionSummary?: ConsumptionSummary | null;
  shiftStart?: string;
  shiftEnd?: string;
  onShiftChange?: (start: string, end: string) => void;
  periodStart?: string;
  periodEnd?: string;
  onPeriodChange?: (start: string, end: string) => void;
}

export function FiltersBar(p: FiltersBarProps) {
  const [consumptionPopoverOpen, setConsumptionPopoverOpen] = useState(false);
  const todaySP = todaySaoPaulo();

  return (
    <div className="relative z-20">
      {consumptionPopoverOpen && (
        <div className="fixed inset-0 z-0 bg-white/40 backdrop-blur-[1px]" aria-hidden="true" />
      )}

      <div className="relative z-10 rounded-2xl border border-border bg-card px-5 py-3 shadow-soft animate-drop-in">
        <div className="flex flex-wrap items-center gap-3">

          {/* Label inline */}
          <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground whitespace-nowrap">
            Filtros
          </span>

          <div className="h-4 w-px bg-border" aria-hidden="true" />

          {/* Switch janela/período */}
          <div className="flex items-center gap-2.5 rounded-full border border-border px-3 py-1.5">
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

          {/* Botões de janela / inputs de data */}
          <div key={p.mode} className="animate-swap-in">
            {p.mode === 'janela' ? (
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
            ) : (
              <div className="flex gap-2">
                <input
                  type="date"
                  className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                  value={p.periodStart ?? todaySP}
                  max={todaySP}
                  onChange={(e) => p.onPeriodChange?.(e.target.value, p.periodEnd ?? todaySP)}
                />
                <input
                  type="date"
                  className="rounded-lg border border-border bg-card px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                  value={p.periodEnd ?? todaySP}
                  min={p.periodStart ?? todaySP}
                  max={todaySP}
                  onChange={(e) => p.onPeriodChange?.(p.periodStart ?? todaySP, e.target.value)}
                />
              </div>
            )}
          </div>

          <div className="flex-1" />

          {/* Bloco de consumo por grupo — apenas no Dashboard */}
          {p.onShiftChange && (
            <>
              <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground whitespace-nowrap">
                Consumo
              </span>
              <div className="h-4 w-px bg-border" aria-hidden="true" />
              <ConsumptionSummaryChip
                summary={p.consumptionSummary}
                shiftStart={p.shiftStart ?? '07:00'}
                shiftEnd={p.shiftEnd ?? '19:00'}
                onApply={p.onShiftChange}
                onOpenChange={setConsumptionPopoverOpen}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default FiltersBar;
