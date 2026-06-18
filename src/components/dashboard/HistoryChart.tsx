import {
  AreaChart, Area, CartesianGrid, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Legend,
} from 'recharts';
import type { SeriesPoint, WindowKey } from '../../types/telemetry';
import { Skeleton } from '../ui/Skeleton';

export interface ChartSeries {
  key: string;
  label: string;
  color: string;   // ex: "var(--primary)"
  data: SeriesPoint[];
}

interface HistoryChartProps {
  title: string;
  unit: string;
  series: ChartSeries[];
  badges?: { label: string; value: string }[];
  windowKey: WindowKey;
  delayMs?: number;
  yDomain?: [number | 'auto', number | 'auto'] | 'smart' | 'robust';
  chartHeightClass?: string;
  yAxisWidth?: number;
  lineType?: 'monotone' | 'linear' | 'stepAfter';
  tooltipNote?: string;
  loading?: boolean;
  referenceLines?: Array<{ value: number; label: string; color: string }>;
}

function formatTime(ts: number, win: WindowKey) {
  const d = new Date(ts);
  if (win === '7d' || win === '30d') {
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function niceMax(rawMax: number): number {
  if (rawMax <= 0) return 10;
  const step = rawMax < 10 ? 1 : rawMax < 50 ? 5 : rawMax < 100 ? 10 : rawMax < 500 ? 50 : 100;
  return (Math.floor(rawMax / step) + 1) * step;
}

function niceFloor(val: number): number {
  if (val <= 0) return 0;
  const step = val < 10 ? 1 : val < 50 ? 5 : val < 100 ? 10 : val < 500 ? 25 : 50;
  return Math.floor(val / step) * step;
}

function yTickFmt(v: number): string {
  if (!isFinite(v)) return '';
  if (v >= 100) return Math.round(v).toString();
  if (v >= 10)  return parseFloat(v.toFixed(1)).toString();
  return parseFloat(v.toFixed(2)).toString();
}

export function HistoryChart({
  title, unit, series, badges, windowKey, delayMs = 0,
  yDomain, lineType = 'monotone', tooltipNote, loading, referenceLines,
  chartHeightClass = 'h-[240px]', yAxisWidth = 36,
}: HistoryChartProps) {

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="space-y-2">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="h-5 w-44" />
          </div>
          <div className="flex gap-2">
            {badges?.map((_, i) => <Skeleton key={i} className="h-6 w-20 rounded-full" />)}
          </div>
        </div>
        <Skeleton className="h-[240px] w-full rounded-xl" />
      </div>
    );
  }

  // Merge por timestamp (não por índice): remotas podem reportar em
  // instantes diferentes. Valor ausente fica null (gap), não 0.
  const lookups = series.map((s) => {
    const m = new Map<number, number>();
    s.data.forEach((p) => m.set(p.t, p.v));
    return m;
  });
  const allTs = Array.from(
    new Set(series.flatMap((s) => s.data.map((p) => p.t))),
  ).sort((a, b) => a - b);
  const data = allTs.map((t) => {
    const row: Record<string, number | null> = { t };
    series.forEach((s, i) => { row[s.key] = lookups[i].get(t) ?? null; });
    return row;
  });

  let resolvedDomain: [number, number] | [number, 'auto'] | ['auto', 'auto'] | undefined = undefined;
  if (yDomain === 'smart') {
    resolvedDomain = [
      ((dataMin: number) => Math.max(0, niceFloor(dataMin * 0.9))) as unknown as number,
      ((dataMax: number) => niceMax(dataMax)) as unknown as number,
    ] as [number, number];
  } else if (yDomain === 'robust') {
    const allValues = series.flatMap((s) => s.data.map((p) => p.v))
      .filter((v): v is number => v != null && isFinite(v) && v >= 0)
      .sort((a, b) => a - b);
    const idx = Math.max(0, Math.ceil(allValues.length * 0.95) - 1);
    resolvedDomain = [0, niceMax(allValues[idx] ?? 0)];
  } else if (Array.isArray(yDomain) && yDomain[0] === 0 && yDomain[1] === 'auto') {
    const allValues = series.flatMap((s) => s.data.map((p) => p.v))
      .filter((v): v is number => v != null && isFinite(v));
    resolvedDomain = [0, niceMax(allValues.length ? Math.max(...allValues) : 0)];
  } else if (yDomain) {
    resolvedDomain = yDomain as [number, number];
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipContent = (props: any) => {
    const { active, payload, label } = props;
    if (!active || !payload?.length) return null;
    const accentColor = payload[0]?.stroke ?? 'hsl(var(--primary))';
    return (
      <div style={{
        background: 'hsl(var(--card))',
        border: '1px solid hsl(var(--border))',
        borderLeft: `3px solid ${accentColor}`,
        borderRadius: 10,
        padding: '10px 14px',
        boxShadow: 'var(--shadow-soft)',
        fontSize: 12,
        minWidth: 164,
      }}>
        <p style={{ marginBottom: 8, color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>
          {formatTime(Number(label), windowKey)}
        </p>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {payload.map((entry: any) => (
          <div key={entry.dataKey} style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '3px 0' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: entry.stroke, flexShrink: 0 }} />
            <span style={{ color: 'hsl(var(--muted-foreground))', flex: 1 }}>{entry.name}</span>
            <span style={{ fontWeight: 700, color: 'hsl(var(--foreground))', fontVariantNumeric: 'tabular-nums' }}>
              {(+(entry.value ?? 0)).toFixed(2)} {unit}
            </span>
          </div>
        ))}
        {tooltipNote && (
          <p style={{
            marginTop: 8, paddingTop: 6,
            borderTop: '1px solid hsl(var(--border))',
            fontSize: 10, color: 'hsl(var(--muted-foreground))', fontStyle: 'italic',
          }}>
            {tooltipNote}
          </p>
        )}
      </div>
    );
  };

  return (
    <div
      className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Histórico</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {badges?.map((b, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-foreground tabular-nums"
            >
              <span className="text-muted-foreground">{b.label}:</span> {b.value}
            </span>
          ))}
        </div>
      </div>

      <div className={`${chartHeightClass} w-full`}>
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
            <defs>
              {series.map((s) => (
                <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor={`hsl(${s.color})`} stopOpacity={0.18} />
                  <stop offset="100%" stopColor={`hsl(${s.color})`} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>

            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 4" vertical={false} />

            <XAxis
              dataKey="t"
              tickFormatter={(v: number) => formatTime(v, windowKey)}
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              minTickGap={32}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={yAxisWidth}
              tickCount={6}
              tickFormatter={yTickFmt}
              domain={resolvedDomain}
              allowDataOverflow={yDomain === 'robust'}
            />

            <Tooltip content={tooltipContent} />

            {referenceLines?.map((rl) => (
              <ReferenceLine
                key={rl.value}
                y={rl.value}
                stroke={rl.color}
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{
                  value: rl.label,
                  position: 'insideTopRight',
                  fontSize: 10,
                  fill: rl.color,
                  fontWeight: 600,
                  dy: -4,
                }}
              />
            ))}

            {series.length > 1 && (
              <Legend
                verticalAlign="top"
                height={28}
                iconType="circle"
                wrapperStyle={{ fontSize: 11, color: 'hsl(var(--muted-foreground))' }}
              />
            )}

            {series.map((s) => (
              <Area
                key={s.key}
                type={lineType}
                dataKey={s.key}
                name={s.label}
                stroke={`hsl(${s.color})`}
                strokeWidth={2}
                fill={`url(#grad-${s.key})`}
                fillOpacity={1}
                activeDot={{ r: 5, strokeWidth: 2, stroke: 'hsl(var(--card))' }}
                isAnimationActive={false}
                connectNulls={true}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default HistoryChart;
