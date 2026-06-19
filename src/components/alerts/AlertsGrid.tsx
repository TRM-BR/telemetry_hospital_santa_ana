import { AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SeverityBadge, StatusBadge } from './AlertBadge';
import type { AlertItem, AlertSeverity } from '@/types/alerts';

const SEVERITY_ICON: Record<AlertSeverity, typeof AlertCircle> = {
  critical:  AlertCircle,
  attention: AlertTriangle,
  info:      Info,
};

const SEVERITY_BORDER: Record<AlertSeverity, string> = {
  critical:  'border-destructive/30',
  attention: 'border-amber-500/30',
  info:      'border-border',
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

interface Props {
  alerts: AlertItem[];
  onSelect: (alert: AlertItem) => void;
}

export function AlertsGrid({ alerts, onSelect }: Props) {
  if (alerts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-card p-12 text-center">
        <p className="text-sm text-muted-foreground">Nenhum alerta encontrado.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {alerts.map((alert) => {
        const Icon = SEVERITY_ICON[alert.severity];
        return (
          <button
            key={alert.id}
            type="button"
            onClick={() => onSelect(alert)}
            className={cn(
              'group text-left rounded-2xl border bg-card p-4 shadow-soft transition-shadow hover:shadow-card cursor-pointer',
              SEVERITY_BORDER[alert.severity],
              !alert.viewed && 'ring-1 ring-primary/10',
            )}
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <Icon className={cn(
                'h-4 w-4 flex-shrink-0 mt-0.5',
                alert.severity === 'critical'  && 'text-destructive',
                alert.severity === 'attention' && 'text-amber-600',
                alert.severity === 'info'      && 'text-primary',
              )} />
              <div className="flex flex-wrap gap-1 justify-end">
                <SeverityBadge severity={alert.severity} />
                <StatusBadge status={alert.status} />
              </div>
            </div>

            <p className={cn('text-sm font-medium text-foreground leading-snug', !alert.viewed && 'font-semibold')}>
              {alert.title}
            </p>
            <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">{alert.description}</p>

            <p className="mt-3 text-[10px] text-muted-foreground">
              {fmtDate(alert.last_triggered_at)}
            </p>
          </button>
        );
      })}
    </div>
  );
}
