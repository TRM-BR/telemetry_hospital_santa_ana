import type { LucideIcon } from 'lucide-react';
import { cn } from '../../lib/cn';
import { useCountUp } from '../../hooks/useCountUp';

type Tone = 'default' | 'accent' | 'danger';

interface KpiCardProps {
  icon: LucideIcon;
  label: string;
  /** Valor numérico animado. Se undefined, exibe `textValue`. */
  value?: number;
  /** Valor textual fixo (não animado). Usado quando não é número puro. */
  textValue?: string;
  suffix?: string;
  decimals?: number;
  spark?: number[];
  delayMs?: number;
  tone?: Tone;
}

const toneGlow: Record<Tone, string> = {
  default: 'from-primary-glow/40 to-primary/20',
  accent:  'from-amber-400/40 to-amber-300/20',
  danger:  'from-destructive/40 to-destructive/20',
};

const toneIcon: Record<Tone, string> = {
  default: 'text-primary bg-secondary',
  accent:  'text-amber-600 bg-amber-50',
  danger:  'text-destructive bg-destructive/10',
};

export function KpiCard({
  icon: Icon,
  label,
  value,
  textValue,
  suffix,
  decimals = 0,
  spark,
  delayMs = 0,
  tone = 'default',
}: KpiCardProps) {
  const animated = useCountUp(value ?? 0, 900);
  const displayValue = value !== undefined ? animated.toFixed(decimals) : (textValue ?? '—');

  const sparkId = `spark-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

  return (
    <div
      className="group relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* Glow decorativo no canto superior direito */}
      <div
        className={cn(
          'pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full bg-gradient-to-br opacity-50 blur-2xl',
          toneGlow[tone],
        )}
      />

      <div className="relative flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground truncate">{label}</p>
          <p className="mt-2 text-3xl font-bold tabular-nums text-foreground leading-none">
            {displayValue}
            {suffix && (
              <span className="ml-1 text-sm font-medium text-muted-foreground">{suffix}</span>
            )}
          </p>
        </div>
        <div className={cn('ml-3 flex-shrink-0 rounded-xl p-2.5', toneIcon[tone])}>
          <Icon className="h-5 w-5" />
        </div>
      </div>

      {/* Sparkline SVG */}
      {spark && spark.length > 1 && (() => {
        const min = Math.min(...spark);
        const max = Math.max(...spark);
        const range = max - min || 1;
        const pts = spark
          .map((v, i) => {
            const x = (i / (spark.length - 1)) * 100;
            const y = 26 - ((v - min) / range) * 22 - 2;
            return `${x.toFixed(2)},${y.toFixed(2)}`;
          })
          .join(' ');

        return (
          <svg viewBox="0 0 100 28" className="mt-4 h-7 w-full" preserveAspectRatio="none">
            <defs>
              <linearGradient id={sparkId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--primary-glow))" stopOpacity="0.35" />
                <stop offset="100%" stopColor="hsl(var(--primary-glow))" stopOpacity="0" />
              </linearGradient>
            </defs>
            <polygon points={`0,28 ${pts} 100,28`} fill={`url(#${sparkId})`} />
            <polyline
              points={pts}
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
