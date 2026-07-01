import {
  BarChart, Bar, CartesianGrid, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { EnergyBar, EnergyWindowKey } from '../../types/energy';
import { cn } from '../../lib/cn';

interface EnergyBalanceChartProps {
  bars: EnergyBar[];
  windowKey: EnergyWindowKey;
  delayMs?: number;
  chartHeightClass?: string;
  muted?: boolean;
  lastSeenUtc?: string | null;
}

function formatTime(ts: number, win: EnergyWindowKey): string {
  const d = new Date(ts);
  if (win === '7d' || win === '30d') {
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
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
  if (abs >= 1000) return `${(v / 1000).toFixed(1)}M`;
  if (abs >= 1) return v.toFixed(1);
  return v.toFixed(3);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TooltipContent({ active, payload, label: ts }: any) {
  if (!active || !payload?.length) return null;
  const gen = payload.find((p: { dataKey: string }) => p.dataKey === 'generated')?.value as number | undefined;
  const con = payload.find((p: { dataKey: string }) => p.dataKey === 'consumed')?.value as number | undefined;
  const time = new Date(Number(ts)).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });
  return (
    <div style={{
      background: 'hsl(var(--card))',
      border: '1px solid hsl(var(--border))',
      borderRadius: 10,
      padding: '10px 14px',
      boxShadow: 'var(--shadow-soft)',
      fontSize: 12,
      minWidth: 180,
    }}>
      <p style={{ marginBottom: 8, color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>{time}</p>
      {gen !== undefined && gen > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'hsl(var(--primary))', flexShrink: 0 }} />
          <span style={{ color: 'hsl(var(--muted-foreground))', flex: 1 }}>Geração</span>
          <span style={{ fontWeight: 700, color: 'hsl(var(--primary))', fontVariantNumeric: 'tabular-nums' }}>
            +{gen.toFixed(3)} kWh
          </span>
        </div>
      )}
      {con !== undefined && con > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'hsl(var(--destructive))', flexShrink: 0 }} />
          <span style={{ color: 'hsl(var(--muted-foreground))', flex: 1 }}>Consumo</span>
          <span style={{ fontWeight: 700, color: 'hsl(var(--destructive))', fontVariantNumeric: 'tabular-nums' }}>
            {(-con).toFixed(3)} kWh
          </span>
        </div>
      )}
    </div>
  );
}

export function EnergyBalanceChart({
  bars,
  windowKey,
  delayMs = 0,
  chartHeightClass = 'h-[280px]',
  muted,
  lastSeenUtc,
}: EnergyBalanceChartProps) {
  const chartData = bars.map((b) => ({
    t: b.t,
    generated: b.generated_kwh,
    consumed: -b.consumed_kwh,
  }));

  return (
    <div
      className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* Header faixa v0 */}
      <div className="flex items-start justify-between gap-4 border-b border-border bg-muted/30 px-5 py-4">
        <div>
          <h3 className="text-base font-semibold text-foreground">Balanço energético</h3>
          <p className="mt-1 text-sm text-muted-foreground">Geração vs. consumo ao longo do período</p>
        </div>
        <div className="flex items-center gap-4 pt-0.5">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <span className="inline-block size-2.5 rounded-full bg-primary" />
            Geração
          </span>
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <span className="inline-block size-2.5 rounded-full bg-destructive" />
            Consumo
          </span>
        </div>
      </div>

      {/* Chart */}
      <div className="relative px-2 pt-4 pb-1">
        {muted && (
          <div className="absolute inset-0 z-10 flex items-center justify-center">
            <span className="rounded-md border border-border bg-card/90 px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur-sm">
              Sem sinal · últimos dados:{' '}
              <span className="tabular-nums text-foreground/70">{formatLastSeen(lastSeenUtc)}</span>
            </span>
          </div>
        )}

        <div className={cn('relative w-full transition-all', chartHeightClass, muted && 'opacity-50 grayscale')}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: 4 }} barCategoryGap="22%">
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 4" vertical={false} />

              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickFormatter={(v: number) => formatTime(v, windowKey)}
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                minTickGap={44}
              />
              <YAxis
                stroke="hsl(var(--muted-foreground))"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={52}
                tickCount={7}
                tickFormatter={yTickFmt}
                unit=" kWh"
              />

              <Tooltip
                content={<TooltipContent />}
                cursor={{ fill: 'hsl(var(--muted))', fillOpacity: 0.35 }}
              />

              <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />

              <Bar
                dataKey="generated"
                name="Geração"
                fill="hsl(var(--primary))"
                fillOpacity={0.8}
                isAnimationActive={false}
                radius={[3, 3, 0, 0]}
                stackId="stack"
              />
              <Bar
                dataKey="consumed"
                name="Consumo"
                fill="hsl(var(--destructive))"
                fillOpacity={0.8}
                isAnimationActive={false}
                radius={[0, 0, 3, 3]}
                stackId="stack"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Footer ↑ geração / ↓ consumo */}
      <div className="flex items-center justify-between px-5 pb-3 pt-1 text-[0.7rem] font-medium uppercase tracking-wide">
        <span className="text-primary">↑ geração</span>
        <span className="text-destructive">↓ consumo</span>
      </div>
    </div>
  );
}

export default EnergyBalanceChart;
