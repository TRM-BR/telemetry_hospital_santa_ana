import { RefreshCw } from 'lucide-react';
import { Switch } from '../ui/Switch';
import type { WindowKey, FilterMode } from '../../types/telemetry';
import { WINDOW_OPTIONS } from '../../constants/dashboard';
import { cn } from '../../lib/cn';

interface FiltersBarProps {
  mode: FilterMode;
  onModeChange: (m: FilterMode) => void;
  windowKey: WindowKey;
  onWindowChange: (w: WindowKey) => void;
  onRefresh: () => void;
}

export function FiltersBar(p: FiltersBarProps) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
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
                defaultValue={new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10)}
              />
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-2">Fim</p>
              <input
                type="date"
                className="rounded-lg border border-border bg-card px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                defaultValue={new Date().toISOString().slice(0, 10)}
              />
            </div>
          </div>
        )}

        <div className="flex-1" />

        <button
          type="button"
          onClick={p.onRefresh}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-4 py-2 text-sm font-medium text-foreground hover:border-primary/40 hover:text-primary transition-colors ml-auto"
        >
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </div>
    </div>
  );
}

export default FiltersBar;
