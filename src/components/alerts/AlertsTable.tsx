import { Eye, EyeOff, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { SeverityBadge, StatusBadge } from './AlertBadge';
import { useToggleAlertViewed } from '@/hooks/useAlerts';
import type { AlertItem } from '@/types/alerts';

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

interface Props {
  alerts: AlertItem[];
  onSelect: (alert: AlertItem) => void;
}

export function AlertsTable({ alerts, onSelect }: Props) {
  const toggle = useToggleAlertViewed();

  if (alerts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border bg-card p-12 text-center">
        <p className="text-sm text-muted-foreground">Nenhum alerta encontrado.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-soft">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-secondary/50 text-left">
              <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Severidade</th>
              <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Título</th>
              <th className="hidden md:table-cell px-4 py-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Status</th>
              <th className="hidden lg:table-cell px-4 py-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Último gatilho</th>
              <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Visto</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {alerts.map((alert) => (
              <tr
                key={alert.id}
                className={cn(
                  'group transition-colors hover:bg-secondary/40 cursor-pointer',
                  !alert.viewed && 'bg-primary/[0.02]',
                )}
                onClick={() => onSelect(alert)}
              >
                <td className="px-4 py-3">
                  <SeverityBadge severity={alert.severity} />
                </td>
                <td className="px-4 py-3">
                  <p className={cn('font-medium text-foreground leading-snug', !alert.viewed && 'font-semibold')}>
                    {alert.title}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-1">{alert.description}</p>
                </td>
                <td className="hidden md:table-cell px-4 py-3">
                  <StatusBadge status={alert.status} />
                </td>
                <td className="hidden lg:table-cell px-4 py-3 text-[12px] text-muted-foreground whitespace-nowrap">
                  {fmtDate(alert.last_triggered_at)}
                </td>
                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    title={alert.viewed ? 'Marcar como não visto' : 'Marcar como visto'}
                    onClick={() => toggle.mutate({ id: alert.id, viewed: !alert.viewed })}
                    disabled={toggle.isPending}
                  >
                    {alert.viewed
                      ? <Eye className="h-3.5 w-3.5 text-muted-foreground" />
                      : <EyeOff className="h-3.5 w-3.5 text-muted-foreground" />
                    }
                  </Button>
                </td>
                <td className="px-4 py-3">
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
