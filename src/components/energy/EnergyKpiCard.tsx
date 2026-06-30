import { useId } from 'react';
import type { LucideIcon } from 'lucide-react';
import { useCountUp } from '../../hooks/useCountUp';
import { cn } from '../../lib/cn';
import { Skeleton } from '../ui/Skeleton';

export type EnergyKpiTone = 'default' | 'primary' | 'danger' | 'accent';

interface EnergyKpiCardProps {
  label: string;
  value: number;
  unit?: string;
  decimals?: number;
  icon: LucideIcon;
  tone?: EnergyKpiTone;
  hint?: string;
  hintTone?: EnergyKpiTone;
  spark?: number[];
  featured?: boolean;
  loading?: boolean;
  delayMs?: number;
}

const toneText: Record<EnergyKpiTone, string> = {
  default: 'text-foreground',
  accent:  'text-accent',
  danger:  'text-destructive',
  primary: 'text-primary',
};

const toneIconBg: Record<EnergyKpiTone, string> = {
  default: 'bg-muted text-muted-foreground',
  accent:  'bg-accent/10 text-accent',
  danger:  'bg-destructive/10 text-destructive',
  primary: 'bg-primary/10 text-primary',
};

const toneStroke: Record<EnergyKpiTone, string> = {
  default: 'hsl(var(--muted-foreground))',
  accent:  'hsl(var(--accent))',
  danger:  'hsl(var(--destructive))',
  primary: 'hsl(var(--primary))',
};

function fmtNum(value: number, decimals = 0): string {
  return value.toLocaleString('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

interface SparklineProps {
  data: number[];
  stroke: string;
}

function Sparkline({ data, stroke }: SparklineProps) {
  const id = useId();
  const W = 100;
  const H = 32;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / range) * (H - 4) - 2;
    return [x, y] as const;
  });

  const line = pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const area = `0,${H} ${line} ${W},${H}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="h-8 w-full"
      aria-hidden
    >
      <defs>
        <linearGradient id={`espark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={stroke} stopOpacity={0.18} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#espark-${id})`} />
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function EnergyKpiCard({
  label,
  value,
  unit,
  decimals = 0,
  icon: Icon,
  tone = 'default',
  hint,
  hintTone = 'default',
  spark,
  featured = false,
  loading,
  delayMs = 0,
}: EnergyKpiCardProps) {
  const animated = useCountUp(value, 650);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-start justify-between gap-3 p-5">
          <div className="space-y-2.5">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className={cn('w-28', featured ? 'h-9' : 'h-7')} />
          </div>
          <Skeleton className="h-9 w-9 rounded-lg" />
        </div>
        {spark !== undefined && <Skeleton className="mx-5 mb-4 h-8 rounded" />}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-shadow hover:shadow-md animate-drop-in',
        featured && 'ring-1 ring-border',
      )}
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {featured && (
        <span
          aria-hidden
          className={cn(
            'absolute inset-x-0 top-0 h-0.5',
            tone === 'danger' ? 'bg-destructive'
            : tone === 'accent' ? 'bg-accent'
            : 'bg-primary',
          )}
        />
      )}

      <div className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0">
          <p className="text-[0.8rem] font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </p>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span
              className={cn(
                'font-semibold tabular-nums tracking-tight',
                featured ? 'text-3xl' : 'text-2xl',
                toneText[tone],
              )}
            >
              {fmtNum(animated, decimals)}
            </span>
            {unit && (
              <span className="text-sm font-medium text-muted-foreground">{unit}</span>
            )}
          </div>

          {hint && (
            <p className={cn('mt-2 text-xs', toneText[hintTone])}>
              {hint}
            </p>
          )}
        </div>

        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-lg',
            toneIconBg[tone],
          )}
        >
          <Icon className="size-[18px]" />
        </span>
      </div>

      {spark && spark.length > 1 && (
        <div className="px-5 pb-4">
          <Sparkline data={spark} stroke={toneStroke[tone]} />
        </div>
      )}
    </div>
  );
}

export default EnergyKpiCard;
