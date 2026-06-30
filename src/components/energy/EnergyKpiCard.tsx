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
  hintIcon?: LucideIcon;
  spark?: number[];
  featured?: boolean;
  loading?: boolean;
  muted?: boolean;
  delayMs?: number;
}

const toneText: Record<EnergyKpiTone, string> = {
  default: 'text-foreground',
  accent:  'text-accent',
  danger:  'text-destructive',
  primary: 'text-primary',
};

const toneIconBg: Record<EnergyKpiTone, string> = {
  default: 'bg-muted-foreground/10 text-muted-foreground',
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

const toneSolid: Record<EnergyKpiTone, string> = {
  default: 'hsl(var(--muted-foreground))',
  accent:  'hsl(var(--accent))',
  danger:  'hsl(var(--destructive))',
  primary: 'hsl(var(--primary))',
};

const toneShadow: Record<EnergyKpiTone, string> = {
  default: '0 1px 2px hsl(220 40% 15% / 0.04), 0 8px 24px -12px hsl(220 40% 15% / 0.10)',
  primary: '0 1px 2px hsl(var(--primary) / 0.05), 0 8px 24px -12px hsl(var(--primary) / 0.18)',
  danger:  '0 1px 2px hsl(var(--destructive) / 0.05), 0 8px 24px -12px hsl(var(--destructive) / 0.16)',
  accent:  '0 1px 2px hsl(var(--accent) / 0.05), 0 8px 24px -12px hsl(var(--accent) / 0.18)',
};

const toneShadowHover: Record<EnergyKpiTone, string> = {
  default: '0 2px 4px hsl(220 40% 15% / 0.06), 0 16px 36px -12px hsl(220 40% 15% / 0.14)',
  primary: '0 2px 4px hsl(var(--primary) / 0.08), 0 16px 36px -12px hsl(var(--primary) / 0.24)',
  danger:  '0 2px 4px hsl(var(--destructive) / 0.08), 0 16px 36px -12px hsl(var(--destructive) / 0.22)',
  accent:  '0 2px 4px hsl(var(--accent) / 0.08), 0 16px 36px -12px hsl(var(--accent) / 0.24)',
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
  const last = pts[pts.length - 1];

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="h-8 w-full"
      aria-hidden
    >
      <defs>
        <linearGradient id={`espark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={stroke} stopOpacity={0.22} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#espark-${id})`} />
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      {last && (
        <circle
          cx={last[0]}
          cy={last[1]}
          r={2.4}
          fill={stroke}
          vectorEffect="non-scaling-stroke"
        />
      )}
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
  hintIcon: HintIcon,
  spark,
  featured = false,
  loading,
  muted = false,
  delayMs = 0,
}: EnergyKpiCardProps) {
  const animated = useCountUp(value, 650);

  if (loading) {
    return (
      <div
        className="rounded-[14px] border border-border bg-card"
        style={{ boxShadow: toneShadow[tone] }}
      >
        <div className="flex items-start justify-between gap-3 p-5">
          <div className="space-y-2.5">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className={cn('w-28', featured ? 'h-9' : 'h-7')} />
          </div>
          <Skeleton className="h-9 w-9 rounded-[10px]" />
        </div>
        {spark !== undefined && <Skeleton className="mx-5 mb-4 h-8 rounded" />}
      </div>
    );
  }

  const isActivePill = hintTone !== 'default';

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-[14px] border border-border bg-card animate-drop-in',
        'transition-[box-shadow,opacity,filter] duration-300',
        featured && 'ring-1 ring-border',
        muted && 'opacity-60 grayscale',
      )}
      style={{
        boxShadow: toneShadow[tone],
        animationDelay: `${delayMs}ms`,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = toneShadowHover[tone];
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.boxShadow = toneShadow[tone];
      }}
    >
      {/* Barra de acento em gradiente */}
      {featured && (
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-[3px]"
          style={{
            background: `linear-gradient(90deg, ${toneSolid[tone]}, transparent)`,
          }}
        />
      )}

      <div className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0">
          <p className="text-[0.75rem] font-medium uppercase tracking-[0.06em] text-muted-foreground">
            {label}
          </p>

          {/* Número editorial */}
          <div className="mt-2 flex items-baseline gap-1.5">
            <span
              className={cn(
                'font-medium tabular-nums tracking-tight',
                featured ? 'text-[1.9rem] leading-none' : 'text-2xl',
                toneText[tone],
              )}
            >
              {fmtNum(animated, decimals)}
            </span>
            {unit && (
              <span className="text-sm font-normal text-muted-foreground">{unit}</span>
            )}
          </div>

          {/* Hint: pill colorida quando hintTone ativo, texto discreto quando default */}
          {hint && (
            <div className="mt-2">
              {isActivePill ? (
                <span
                  className={cn(
                    'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium',
                    hintTone === 'danger'
                      ? 'bg-destructive/10 text-destructive'
                      : hintTone === 'accent'
                      ? 'bg-accent/10 text-accent'
                      : 'bg-primary/10 text-primary',
                  )}
                >
                  {HintIcon && <HintIcon className="size-3" />}
                  {hint}
                </span>
              ) : (
                <p className="text-xs text-muted-foreground">{hint}</p>
              )}
            </div>
          )}
        </div>

        {/* Chip de ícone premium */}
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-[10px] ring-1 ring-inset',
            toneIconBg[tone],
            tone === 'default'
              ? 'ring-muted-foreground/10'
              : tone === 'primary'
              ? 'ring-primary/15'
              : tone === 'danger'
              ? 'ring-destructive/15'
              : 'ring-accent/15',
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
