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
  featured?: boolean;
  hint?: string;
  hintTone?: 'default' | 'accent' | 'danger';
}

const TONE_RING = {
  default: 'from-primary-glow/40 to-primary/30',
  accent:  'from-accent/50 to-accent/20',
  danger:  'from-destructive/50 to-destructive/20',
} as const;

const TONE_COLOR = {
  default: 'hsl(var(--primary))',
  accent:  'hsl(var(--accent))',
  danger:  'hsl(var(--destructive))',
} as const;

const TONE_GRAD = {
  default: 'hsl(var(--primary-glow))',
  accent:  'hsl(var(--accent))',
  danger:  'hsl(var(--destructive))',
} as const;

const HINT_CLS = {
  default: 'text-muted-foreground',
  accent:  'text-accent',
  danger:  'text-destructive',
} as const;

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
  featured,
  hint,
  hintTone = 'default',
}: KpiCardProps) {
  const animated = useCountUp(value, 1000);
  const display = animated.toFixed(decimals);

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
        <div className="flex items-start justify-between">
          <div className="space-y-2.5">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className={cn('w-28', featured ? 'h-11' : 'h-9')} />
          </div>
          <Skeleton className="h-10 w-10 rounded-xl" />
        </div>
        {spark !== undefined && <Skeleton className="mt-4 h-7 w-full rounded" />}
      </div>
    );
  }

  const accentColor = TONE_COLOR[tone];
  const gradId = `spark-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

  return (
    <div
      className="group relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {featured && (
        <div
          className="absolute inset-x-0 top-0 h-[3px] rounded-t-2xl"
          style={{ background: accentColor }}
        />
      )}
      <div
        className={cn(
          'pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full bg-gradient-to-br opacity-60 blur-2xl',
          TONE_RING[tone],
        )}
      />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className={cn('mt-2 font-bold tabular-nums text-foreground', featured ? 'text-4xl' : 'text-3xl')}>
            {display}
            {suffix && <span className="ml-1 text-sm font-medium text-muted-foreground">{suffix}</span>}
          </p>
          {hint && (
            <p className={cn('mt-1 text-[11px] font-medium', HINT_CLS[hintTone])}>{hint}</p>
          )}
        </div>
        <div className="rounded-xl bg-secondary p-2.5 text-primary">
          <Icon className="h-5 w-5" />
        </div>
      </div>

      {spark && spark.length > 1 && (() => {
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
                <stop offset="0%" stopColor={TONE_GRAD[tone]} stopOpacity="0.35" />
                <stop offset="100%" stopColor={TONE_GRAD[tone]} stopOpacity="0" />
              </linearGradient>
            </defs>
            <polygon points={`0,28 ${points} 100,28`} fill={`url(#${gradId})`} />
            <polyline
              points={points}
              fill="none"
              stroke={accentColor}
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
