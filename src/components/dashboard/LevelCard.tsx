import type { ReactNode } from 'react';
import { useCountUp } from '../../hooks/useCountUp';
import { cn } from '../../lib/cn';
import { Skeleton } from '../ui/Skeleton';
import { ReservoirGauge } from './ReservoirGauge';
import type { DashboardSnapshot } from '../../types/telemetry';

interface LevelCardProps {
  snapshot: DashboardSnapshot;
  loading?: boolean;
}

const stateTone: Record<DashboardSnapshot['estado'], string> = {
  Confortável: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  Atenção:     'bg-accent/15      text-accent-foreground border-accent/40',
  Crítico:     'bg-destructive/10 text-destructive border-destructive/40',
  'Sem leitura': 'bg-muted text-muted-foreground border-border',
};

export function LevelCard({ snapshot, loading }: LevelCardProps) {
  const animated = useCountUp(snapshot.nivelAtual, 1100);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
        <Skeleton className="h-5 w-36 mb-4" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Nível atual</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">Reservatórios</h3>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Última leitura:{' '}
          <span className="text-foreground tabular-nums">
            {snapshot.ultimaLeitura.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })}
          </span>
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-6 items-center">
        <div className="flex items-center gap-4">
          <ReservoirGauge level={snapshot.nivelAtual} />
          <div>
            <p className="text-4xl font-bold tabular-nums text-foreground">
              {animated.toFixed(1)}
              <span className="text-xl font-medium text-muted-foreground">%</span>
            </p>
            <span
              className={cn(
                'mt-2 inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider',
                stateTone[snapshot.estado],
              )}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              Estado: {snapshot.estado}
            </span>
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <p className="text-xs font-semibold text-foreground">Análise de consumo</p>
            <p className="text-[11px] text-muted-foreground">Indicadores de desempenho</p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Mini label="Autonomia" value={`${snapshot.autonomiaDias} dias`} />
            <Mini label="Consumo médio" value={`${snapshot.consumoMedio} m³/h`} />
            <Mini label="Consumo atual" value={`${snapshot.consumoAtual} m³/h`} />
          </div>
          <div className="flex flex-wrap gap-2">
            <Chip>Consumo: dentro do padrão</Chip>
            <Chip>Pressão: ok</Chip>
            <Chip>Reservatório: estável</Chip>
          </div>
        </div>
      </div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-3">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground leading-tight">{label}</p>
      <p className="mt-1.5 text-sm font-bold text-foreground tabular-nums">{value}</p>
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 px-2.5 py-1 text-[11px] font-medium">
      {children}
    </span>
  );
}

export default LevelCard;
