import {
  BarChart, Bar, Cell, CartesianGrid, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { SeriesPoint, WindowKey } from '../../types/telemetry';
import { cn } from '../../lib/cn';

interface FlowBarChartProps {
  title: string;
  data: SeriesPoint[];
  unit?: string;
  label?: string;
  windowKey: WindowKey;
  delayMs?: number;
  chartHeightClass?: string;
  muted?: boolean;
  lastSeenUtc?: string | null;
}

function formatTime(ts: number, win: WindowKey) {
  const d = new Date(ts);
  if (win === '7d' || win === '30d') {
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function formatTooltipTime(ts: number): string {
  return new Date(ts).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function formatLastSeen(iso: string | null | undefined): string {
  if (!iso) return 'sem registro';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'sem registro';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}

function yTickFmt(v: number): string {
  if (!isFinite(v)) return '';
  const abs = Math.abs(v);
  if (abs >= 10_000) return `${(v / 1000).toFixed(0)}k`;
  if (abs >= 1_000) return `${(v / 1000).toFixed(1)}k`;
  return Math.round(v).toString();
}

export function FlowBarChart({
  title,
  data,
  unit = 'L/h',
  label = 'Vazão',
  windowKey,
  delayMs = 0,
  chartHeightClass = 'h-[280px]',
  muted,
  lastSeenUtc,
}: FlowBarChartProps) {
  const chartData = data.map((p) => ({ t: p.t, v: p.v }));

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipContent = (props: any) => {
    const { active, payload, label: ts } = props;
    if (!active || !payload?.length) return null;
    const val = payload[0]?.value as number;
    const isPos = val >= 0;
    return (
      <div style={{
        background: 'hsl(var(--card))',
        border: '1px solid hsl(var(--border))',
        borderLeft: `3px solid ${isPos ? 'hsl(var(--primary))' : 'hsl(var(--destructive))'}`,
        borderRadius: 10,
        padding: '10px 14px',
        boxShadow: 'var(--shadow-soft)',
        fontSize: 12,
        minWidth: 164,
      }}>
        <p style={{ marginBottom: 8, color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>
          {formatTooltipTime(Number(ts))}
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: 2,
            background: isPos ? 'hsl(var(--primary))' : 'hsl(var(--destructive))',
            flexShrink: 0,
          }} />
          <span style={{ color: 'hsl(var(--muted-foreground))', flex: 1 }}>{label}</span>
          <span style={{ fontWeight: 700, color: 'hsl(var(--foreground))', fontVariantNumeric: 'tabular-nums' }}>
            {val >= 0 ? '+' : ''}{val.toFixed(0)} {unit}
          </span>
        </div>
        <p style={{
          marginTop: 6, fontSize: 10, color: 'hsl(var(--muted-foreground))', fontStyle: 'italic',
        }}>
          {isPos ? 'Entrada líquida (enchendo)' : 'Saída líquida (consumo)'}
        </p>
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
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Vazão</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3>
          {muted && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              Sem sinal · últimos dados disponíveis:{' '}
              <span className="tabular-nums text-foreground/70">{formatLastSeen(lastSeenUtc)}</span>
            </p>
          )}
        </div>
      </div>

      <div className={cn('w-full transition-all', chartHeightClass, muted && 'opacity-55 grayscale')}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 4" vertical={false} />

            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['auto', 'auto']}
              tickFormatter={(v: number) => formatTime(v, windowKey)}
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={52}
              tickCount={6}
              tickFormatter={yTickFmt}
            />

            <Tooltip content={tooltipContent} cursor={{ fill: 'hsl(var(--muted))', fillOpacity: 0.4 }} />

            <ReferenceLine
              y={0}
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="4 3"
              strokeWidth={1.5}
            />

            <Bar dataKey="v" name={label} isAnimationActive={false} radius={[3, 3, 0, 0]}>
              {chartData.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={entry.v >= 0 ? 'hsl(var(--primary))' : 'hsl(var(--destructive))'}
                  fillOpacity={0.72}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default FlowBarChart;
