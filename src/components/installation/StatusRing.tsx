import type { ReactNode } from 'react';
import { cn } from '../../lib/cn';
import type { InstallationStatus } from '../../types/telemetry';

const ringByStatus: Record<InstallationStatus, string> = {
  online:  'ring-primary-glow/70 shadow-[0_0_40px_-8px_hsl(var(--primary-glow)/0.8)]',
  alert:   'ring-accent/70       shadow-[0_0_40px_-8px_hsl(var(--accent)/0.7)]',
  offline: 'ring-destructive/60  shadow-[0_0_40px_-8px_hsl(var(--destructive)/0.6)]',
};

interface StatusRingProps {
  status: InstallationStatus;
  children: ReactNode;
  size?: 'md' | 'lg';
}

export function StatusRing({ status, children, size = 'lg' }: StatusRingProps) {
  return (
    <div
      className={cn(
        'relative inline-flex items-center justify-center rounded-full bg-white/10 backdrop-blur-sm ring-2 animate-breath',
        size === 'lg' ? 'h-24 w-24' : 'h-16 w-16',
        ringByStatus[status],
      )}
    >
      <span
        className={cn(
          'absolute inset-0 rounded-full animate-ping-slow',
          status === 'online'  && 'bg-primary-glow/30',
          status === 'alert'   && 'bg-accent/30',
          status === 'offline' && 'bg-destructive/25',
        )}
      />
      <div className="relative z-10 text-primary-foreground">{children}</div>
    </div>
  );
}

export default StatusRing;
