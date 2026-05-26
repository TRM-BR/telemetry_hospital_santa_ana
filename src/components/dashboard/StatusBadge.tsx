import type { SystemStatus } from '../../types/telemetry';
import { cn } from '../../lib/cn';

interface StatusBadgeProps {
  status: SystemStatus;
  label?: string;
}

const toneMap: Record<SystemStatus, string> = {
  normal:    'bg-emerald-500/10 border-emerald-500/30 text-emerald-700',
  attention: 'bg-amber-400/10  border-amber-400/40   text-amber-700',
  critical:  'bg-destructive/10 border-destructive/30 text-destructive',
};

const labelMap: Record<SystemStatus, string> = {
  normal:    'Operação normal',
  attention: 'Atenção',
  critical:  'Crítico',
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider',
        toneMap[status],
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label ?? labelMap[status]}
    </span>
  );
}
