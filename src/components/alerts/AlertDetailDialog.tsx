import { CheckCircle, Circle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { SeverityBadge, StatusBadge } from './AlertBadge';
import { useToggleAlertViewed } from '@/hooks/useAlerts';
import type { AlertItem } from '@/types/alerts';

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  });
}

interface Props {
  alert: AlertItem | null;
  open: boolean;
  onClose: () => void;
}

export function AlertDetailDialog({ alert, open, onClose }: Props) {
  const toggle = useToggleAlertViewed();

  if (!alert) return null;

  const relevantEntries = alert.relevant_data
    ? Object.entries(alert.relevant_data)
    : [];

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <SeverityBadge severity={alert.severity} />
            <StatusBadge status={alert.status} />
          </div>
          <DialogTitle>{alert.title}</DialogTitle>
          <DialogDescription>{alert.description}</DialogDescription>
        </DialogHeader>

        <div className="mt-4 space-y-4 text-sm">
          {/* Timestamps */}
          <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-secondary/50 p-4">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">Primeiro gatilho</p>
              <p className="text-foreground font-medium">{fmtDate(alert.first_triggered_at)}</p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">Último gatilho</p>
              <p className="text-foreground font-medium">{fmtDate(alert.last_triggered_at)}</p>
            </div>
            {alert.resolved_at && (
              <div className="col-span-2">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-0.5">Resolvido em</p>
                <p className="text-foreground font-medium">{fmtDate(alert.resolved_at)}</p>
              </div>
            )}
          </div>

          {/* Recomendação */}
          {alert.recommendation && (
            <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
              <p className="text-[10px] uppercase tracking-widest text-primary mb-1">Recomendação</p>
              <p className="text-foreground">{alert.recommendation}</p>
            </div>
          )}

          {/* Dados relevantes */}
          {relevantEntries.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-2">Dados técnicos</p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
                {relevantEntries.map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[10px] text-muted-foreground">{k}</dt>
                    <dd className="text-sm font-medium text-foreground">
                      {Array.isArray(v) ? v.join(', ') : String(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {/* Instalação */}
          <p className="text-[11px] text-muted-foreground">
            Instalação: <span className="font-medium text-foreground">{alert.installation_name}</span>
            {' · '}Regra: <code className="font-mono text-xs">{alert.rule_key}</code>
          </p>
        </div>

        {/* Ações */}
        <div className="mt-5 flex justify-between items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => toggle.mutate({ id: alert.id, viewed: !alert.viewed })}
            disabled={toggle.isPending}
            className="gap-1.5"
          >
            {alert.viewed
              ? <><Circle className="h-3.5 w-3.5" /> Marcar como não visto</>
              : <><CheckCircle className="h-3.5 w-3.5" /> Marcar como visto</>
            }
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
