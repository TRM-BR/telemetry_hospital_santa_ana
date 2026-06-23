import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AreaChart, Area, CartesianGrid, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Legend,
} from 'recharts';
import { ZoomIn, RotateCcw } from 'lucide-react';
import type { SeriesPoint, WindowKey } from '../../types/telemetry';
import { Skeleton } from '../ui/Skeleton';
import { cn } from '../../lib/cn';

export interface ChartSeries {
  key: string;
  label: string;
  color: string;   // HSL triplet, e.g. "217 91% 60%"
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
  zoomable?: boolean;
  xDomain?: [number, number];
  muted?: boolean;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function formatTime(ts: number, win: WindowKey) {
  const d = new Date(ts);
  if (win === '7d' || win === '30d') {
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function formatTooltipTime(ts: number, spanDays: number): string {
  const d = new Date(ts);
  if (spanDays > 365) {
    return d.toLocaleString('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function niceMax(rawMax: number): number {
  if (rawMax <= 0) return 10;
  const step =
    rawMax < 10  ? 1  :
    rawMax < 50  ? 5  :
    rawMax < 100 ? 10 :
    rawMax < 500 ? 50 : 100;
  return (Math.floor(rawMax / step) + 1) * step;
}

function niceFloor(val: number): number {
  if (val <= 0) return 0;
  const step =
    val < 10  ? 1  :
    val < 50  ? 5  :
    val < 100 ? 10 :
    val < 500 ? 25 : 50;
  return Math.floor(val / step) * step;
}

function yTickFmt(v: number): string {
  if (!isFinite(v)) return '';
  if (v >= 100) return Math.round(v).toString();
  if (v >= 10)  return parseFloat(v.toFixed(1)).toString();
  return parseFloat(v.toFixed(2)).toString();
}

// ── component ─────────────────────────────────────────────────────────────────

export function HistoryChart({
  title, unit, series, badges, windowKey, delayMs = 0,
  yDomain, lineType = 'monotone', tooltipNote, loading, referenceLines,
  chartHeightClass = 'h-[240px]', yAxisWidth = 36, zoomable = true,
  xDomain, muted,
}: HistoryChartProps) {

  // ── zoom/pan state ─────────────────────────────────────────────────────────
  const [viewDomain, setViewDomain]           = useState<[number, number] | null>(null);
  const [selStart,   setSelStart]             = useState<number | null>(null);
  const [selEnd,     setSelEnd]               = useState<number | null>(null);
  const isSelecting                           = useRef(false);
  const selStartRef                           = useRef<number | null>(null);
  const selEndRef                             = useRef<number | null>(null);
  const isPanning                             = useRef(false);
  const panStartXRef                          = useRef<number>(0);
  const panStartDomainRef                     = useRef<[number, number] | null>(null);
  const [isPanningVisual, setIsPanningVisual] = useState(false);
  const [chartEl, setChartEl]                 = useState<HTMLDivElement | null>(null);
  const allDataRef                            = useRef<Record<string, number | null>[]>([]);
  const viewDomainRef                         = useRef<[number, number] | null>(null);
  viewDomainRef.current = viewDomain;

  const resetZoom = useCallback(() => {
    setViewDomain(null);
    setSelStart(null);
    setSelEnd(null);
    isSelecting.current = false;
  }, []);

  // Native non-passive wheel listener
  useEffect(() => {
    if (!zoomable || !chartEl) return;
    const handler = (e: WheelEvent) => {
      if (allDataRef.current.length < 2) return;
      e.preventDefault();
      const ad        = allDataRef.current;
      const vd        = viewDomainRef.current;
      const dataLo    = ad[0].t as number;
      const dataHi    = ad[ad.length - 1].t as number;
      const [lo, hi]  = vd ?? [dataLo, dataHi];
      const factor    = e.deltaY > 0 ? 1.3 : 0.75;
      const newRange  = (hi - lo) * factor;
      const center    = (lo + hi) / 2;
      if (newRange >= (dataHi - dataLo) * 0.98) { setViewDomain(null); return; }
      setViewDomain([
        Math.max(dataLo, center - newRange / 2),
        Math.min(dataHi, center + newRange / 2),
      ]);
    };
    chartEl.addEventListener('wheel', handler, { passive: false });
    return () => chartEl.removeEventListener('wheel', handler);
  }, [zoomable, chartEl]);

  // ── skeleton ───────────────────────────────────────────────────────────────
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
        <Skeleton className={`${chartHeightClass} w-full rounded-xl`} />
      </div>
    );
  }

  // ── data merge por timestamp (não por índice) ──────────────────────────────
  // Remotas reportam em instantes diferentes → merge por ts, null para gaps.
  const lookups = series.map((s) => {
    const m = new Map<number, number>();
    s.data.forEach((p) => m.set(p.t, p.v));
    return m;
  });
  const allTs = Array.from(
    new Set(series.flatMap((s) => s.data.map((p) => p.t))),
  ).sort((a, b) => a - b);
  const allData = allTs.map((t) => {
    const row: Record<string, number | null> = { t };
    series.forEach((s, i) => { row[s.key] = lookups[i].get(t) ?? null; });
    return row;
  });
  allDataRef.current = allData;

  const spanDays = allData.length >= 2
    ? (viewDomain != null
        ? (viewDomain[1] - viewDomain[0])
        : (allTs[allTs.length - 1] - allTs[0])
      ) / 86_400_000
    : 0;

  const data = viewDomain
    ? allData.filter((d) => (d.t as number) >= viewDomain[0] && (d.t as number) <= viewDomain[1])
    : allData;

  // ── Y domain ───────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let resolvedDomain: any = undefined;
  if (yDomain === 'smart') {
    resolvedDomain = [
      (dataMin: number) => Math.max(0, niceFloor(dataMin * 0.9)),
      (dataMax: number) => niceMax(dataMax),
    ];
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
    resolvedDomain = yDomain;
  }

  // ── handlers ───────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleMouseDown = (state: any, event?: any) => {
    if (!zoomable || !state?.activeLabel) return;
    const button  = (event?.button  ?? 0) as number;
    const clientX = (event?.clientX ?? 0) as number;
    const t = Number(state.activeLabel);
    if (button === 2) {
      isSelecting.current = true;
      selStartRef.current = t;
      selEndRef.current   = null;
      setSelStart(t);
      setSelEnd(null);
    } else if (button === 0) {
      if (allDataRef.current.length < 2) return;
      isPanning.current        = true;
      setIsPanningVisual(true);
      panStartXRef.current     = clientX;
      const ad = allDataRef.current;
      panStartDomainRef.current =
        viewDomainRef.current ?? [ad[0].t as number, ad[ad.length - 1].t as number];
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleMouseMove = (state: any, event?: any) => {
    if (isSelecting.current && state?.activeLabel) {
      const t = Number(state.activeLabel);
      selEndRef.current = t;
      setSelEnd(t);
      return;
    }
    if (isPanning.current && panStartDomainRef.current && event?.clientX != null) {
      const currentX = event.clientX as number;
      const deltaX   = currentX - panStartXRef.current;
      if (Math.abs(deltaX) < 1) return;
      const ad     = allDataRef.current;
      if (ad.length < 2) return;
      const dataLo = ad[0].t as number;
      const dataHi = ad[ad.length - 1].t as number;
      const [lo, hi] = panStartDomainRef.current;
      const range    = hi - lo;
      const effectiveWidth = Math.max(100, (chartEl?.offsetWidth ?? 400) - yAxisWidth - 12);
      const timePerPx = range / effectiveWidth;
      const timeDelta = -deltaX * timePerPx;
      let newLo = lo + timeDelta;
      let newHi = hi + timeDelta;
      if (newLo < dataLo) { newHi = Math.min(dataHi, newHi + (dataLo - newLo)); newLo = dataLo; }
      if (newHi > dataHi) { newLo = Math.max(dataLo, newLo - (newHi - dataHi)); newHi = dataHi; }
      setViewDomain([newLo, newHi]);
      panStartXRef.current      = currentX;
      panStartDomainRef.current = [newLo, newHi];
    }
  };

  const handleMouseUp = () => {
    if (isPanning.current) {
      isPanning.current        = false;
      panStartDomainRef.current = null;
      setIsPanningVisual(false);
      return;
    }
    if (!isSelecting.current) return;
    isSelecting.current = false;
    const l = selStartRef.current;
    const r = selEndRef.current;
    setSelStart(null);
    setSelEnd(null);
    if (l == null || r == null || Math.abs(r - l) < 60_000) return;
    setViewDomain([Math.min(l, r), Math.max(l, r)]);
  };

  const handleDoubleClick = () => { if (viewDomain) resetZoom(); };

  const handleMouseLeave = () => {
    if (isPanning.current) {
      isPanning.current        = false;
      panStartDomainRef.current = null;
      setIsPanningVisual(false);
    }
  };

  // ── tooltip ────────────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipContent = (props: any) => {
    const { active, payload, label } = props;
    if (!active || !payload?.length) return null;
    if (isSelecting.current || isPanning.current) return null;
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
          {formatTooltipTime(Number(label), spanDays)}
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

  const isZoomed = viewDomain != null;

  return (
    <div
      className={cn(
        'rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in',
        muted && 'opacity-60 grayscale transition-all',
      )}
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Histórico</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3>
        </div>
        <div className="flex flex-wrap justify-end items-center gap-2">
          {muted && (
            <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-700">
              Sem sinal
            </span>
          )}
          {badges?.map((b, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-foreground tabular-nums"
            >
              <span className="text-muted-foreground">{b.label}:</span> {b.value}
            </span>
          ))}
          {isZoomed && (
            <button
              type="button"
              onClick={resetZoom}
              title="Resetar zoom (ou double-click no gráfico)"
              className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
            >
              <RotateCcw className="h-3 w-3" />
              Reset
            </button>
          )}
          {zoomable && !isZoomed && (
            <span
              title="Esquerda: navegar · Direita: zoom · Scroll: zoom · 2×: resetar"
              className="inline-flex items-center gap-1 text-[10px] text-muted-foreground/50 select-none"
            >
              <ZoomIn className="h-3 w-3" />
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      <div
        ref={setChartEl}
        className={cn(
          'w-full select-none',
          chartHeightClass,
          zoomable && (isPanningVisual ? 'cursor-grabbing' : 'cursor-grab'),
        )}
        onDoubleClick={handleDoubleClick}
        onMouseLeave={handleMouseLeave}
        onMouseUp={handleMouseUp}
        onContextMenu={(e) => e.preventDefault()}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 8, left: 4, bottom: 0 }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
          >
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
              type="number"
              scale="time"
              domain={viewDomain ?? xDomain ?? ['auto', 'auto']}
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

            {selStart != null && selEnd != null && (
              <ReferenceArea
                x1={selStart}
                x2={selEnd}
                stroke="hsl(var(--primary))"
                strokeOpacity={0.6}
                fill="hsl(var(--primary))"
                fillOpacity={0.08}
              />
            )}

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
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                dot={(props: any): any => {
                  if (props.index !== data.length - 1) return <g key={`e-${props.index}`} />;
                  return (
                    <g key={`ld-${s.key}`}>
                      <circle cx={props.cx} cy={props.cy} r={8}
                        fill={`hsl(${s.color})`} opacity={0.22} />
                      <circle cx={props.cx} cy={props.cy} r={3.5}
                        fill={`hsl(${s.color})`}
                        stroke="hsl(var(--card))" strokeWidth={2} />
                    </g>
                  );
                }}
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
