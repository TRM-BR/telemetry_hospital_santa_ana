import type { LucideIcon } from 'lucide-react';
import { useCountUp } from '../../hooks/useCountUp';
import { cn } from '../../lib/cn';
import { Skeleton } from '../ui/Skeleton';

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  value: number;
  suffix?: string;
  decimals?: number;
  spark?: number[];
  delayMs?: number;
  tone?: 'default' | 'accent' | 'danger';
  loading?: boolean;
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  suffix,
  decimals = 0,
  spark,
  delayMs = 0,
  tone = 'default',
  loading,
}: KpiCardProps) {
  const animated = useCountUp(value, 1000);
  const display = animated.toFixed(decimals);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
        <div className="flex items-start justify-between">
          <div className="space-y-2.5">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="h-9 w-28" />
          </div>
          <Skeleton className="h-10 w-10 rounded-xl" />
        </div>
        {spark !== undefined && <Skeleton className="mt-4 h-7 w-full rounded" />}
      </div>
    );
  }

  const toneRing = {
    default: 'from-primary-glow/40 to-primary/30',
    accent:  'from-accent/50 to-accent/20',
    danger:  'from-destructive/50 to-destructive/20',
  }[tone];

  return (
    <div
      className="group relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div
        className={cn(
          'pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full bg-gradient-to-br opacity-60 blur-2xl',
          toneRing,
        )}
      />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-bold tabular-nums text-foreground">
            {display}
            {suffix && <span className="ml-1 text-sm font-medium text-muted-foreground">{suffix}</span>}
          </p>
        </div>
        <div className="rounded-xl bg-secondary p-2.5 text-primary">
          <Icon className="h-5 w-5" />
        </div>
      </div>

      {spark && spark.length > 1 && (() => {
        const gradId = `spark-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
        const min = Math.min(...spark);
        const max = Math.max(...spark);
        const range = max - min || 1;
        const points = spark
          .map((v, i) => {
            const x = (i / (spark.length - 1)) * 100;
            const y = 28 - ((v - min) / range) * 24 - 2;
            return `${x},${y}`;
          })
          .join(' ');
        return (
          <svg viewBox="0 0 100 28" className="mt-4 h-7 w-full" preserveAspectRatio="none">
            <defs>
              <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.4" />
                <stop offset="100%" stopColor="hsl(var(--primary-glow))" stopOpacity="0" />
              </linearGradient>
            </defs>
            <polygon points={`0,28 ${points} 100,28`} fill={`url(#${gradId})`} />
            <polyline
              points={points}
              fill="none"
              stroke="hsl(var(--primary))"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        );
      })()}
    </div>
  );
}

export default KpiCard;
