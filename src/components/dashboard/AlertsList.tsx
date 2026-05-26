import { AlertTriangle, Info, AlertCircle } from 'lucide-react';
import type { Alert, AlertSeverity } from '../../types/telemetry';
import { cn } from '../../lib/cn';

interface AlertsListProps {
  alerts: Alert[];
  title?: string;
}

const iconMap: Record<AlertSeverity, typeof AlertTriangle> = {
  info:      Info,
  attention: AlertTriangle,
  critical:  AlertCircle,
};

const toneMap: Record<AlertSeverity, { row: string; icon: string }> = {
  info:      { row: 'border-border',         icon: 'text-primary' },
  attention: { row: 'border-accent/40',      icon: 'text-amber-600' },
  critical:  { row: 'border-destructive/40', icon: 'text-destructive' },
};

export function AlertsList({ alerts, title = 'Alertas recentes' }: AlertsListProps) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Alertas</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {alerts.length} evento{alerts.length !== 1 ? 's' : ''}
        </span>
      </div>

      <ul className="space-y-2">
        {alerts.map((alert) => {
          const Icon = iconMap[alert.severity];
          const tone = toneMap[alert.severity];
          return (
            <li
              key={alert.id}
              className={cn(
                'flex items-start gap-3 rounded-xl border px-4 py-3 transition-colors hover:bg-secondary/60',
                tone.row,
              )}
            >
              <Icon className={cn('mt-0.5 h-4 w-4 flex-shrink-0', tone.icon)} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground leading-snug">{alert.message}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">{alert.timeLabel}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default AlertsList;
