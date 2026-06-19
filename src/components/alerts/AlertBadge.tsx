import { Badge } from '@/components/ui/badge';
import type { AlertSeverity, AlertStatus } from '@/types/alerts';

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical:  'Crítico',
  attention: 'Atenção',
  info:      'Info',
};

const STATUS_LABEL: Record<AlertStatus, string> = {
  active:   'Ativo',
  resolved: 'Resolvido',
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <Badge variant={severity}>
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

export function StatusBadge({ status }: { status: AlertStatus }) {
  return (
    <Badge variant={status}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}
