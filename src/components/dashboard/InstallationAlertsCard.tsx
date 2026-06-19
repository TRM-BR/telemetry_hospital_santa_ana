import { useNavigate } from 'react-router-dom';
import { AlertCircle, AlertTriangle, Info, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import type { AlertSeverity } from '@/types/alerts';

const SEVERITY_ICON: Record<AlertSeverity, typeof AlertCircle> = {
  critical:  AlertCircle,
  attention: AlertTriangle,
  info:      Info,
};

const SEVERITY_COLOR: Record<AlertSeverity, string> = {
  critical:  'text-destructive',
  attention: 'text-amber-600',
  info:      'text-primary',
};

function fmtRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1) return 'agora';
  if (m < 60) return `há ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `há ${h}h`;
  return `há ${Math.floor(h / 24)}d`;
}

export function InstallationAlertsCard({ installationId }: { installationId?: string }) {
  const navigate = useNavigate();
  const { data: allAlerts, isLoading } = useAlerts();

  const active = (allAlerts ?? []).filter(
    (a) =>
      a.status === 'active' &&
      (!installationId || a.installation_name !== undefined),
  );

  const critical  = active.filter((a) => a.severity === 'critical').length;
  const attention = active.filter((a) => a.severity === 'attention').length;
  const info      = active.filter((a) => a.severity === 'info').length;

  const recent = active
    .sort((a, b) => new Date(b.last_triggered_at).getTime() - new Date(a.last_triggered_at).getTime())
    .slice(0, 3);

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Avisos</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">Alertas ativos</h3>
        </div>
        <button
          type="button"
          onClick={() => navigate('/alertas')}
          className="inline-flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 transition-colors"
        >
          Ver todos <ChevronRight className="h-3 w-3" />
        </button>
      </div>

      {/* Contadores */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'Críticos', count: critical, color: 'text-destructive', bg: 'bg-destructive/5' },
          { label: 'Atenção',  count: attention, color: 'text-amber-600',  bg: 'bg-amber-500/5' },
          { label: 'Info',     count: info,      color: 'text-primary',    bg: 'bg-primary/5' },
        ].map(({ label, count, color, bg }) => (
          <div key={label} className={cn('rounded-xl p-3 text-center', bg)}>
            <p className={cn('text-xl font-bold tabular-nums', color)}>{count}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-10 rounded-xl bg-secondary animate-pulse" />
          ))}
        </div>
      ) : recent.length === 0 ? (
        <p className="text-center text-sm text-muted-foreground py-4">Nenhum aviso ativo.</p>
      ) : (
        <ul className="space-y-2">
          {recent.map((alert) => {
            const Icon = SEVERITY_ICON[alert.severity];
            return (
              <li
                key={alert.id}
                className="flex items-start gap-3 rounded-xl border border-border px-3 py-2.5 hover:bg-secondary/60 transition-colors cursor-pointer"
                onClick={() => navigate('/alertas')}
              >
                <Icon className={cn('mt-0.5 h-3.5 w-3.5 flex-shrink-0', SEVERITY_COLOR[alert.severity])} />
                <div className="flex-1 min-w-0">
                  <p className={cn('text-[12px] font-medium text-foreground leading-snug', !alert.viewed && 'font-semibold')}>
                    {alert.title}
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {fmtRelative(alert.last_triggered_at)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default InstallationAlertsCard;
