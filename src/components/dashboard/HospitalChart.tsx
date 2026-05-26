import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import type { HourlyPoint } from '../../types/telemetry';

interface ChartSeries {
  data: HourlyPoint[];
  color: string;
  label: string;
  key: string;
}

interface HospitalChartProps {
  title: string;
  subtitle?: string;
  unit: string;
  yDomain?: [number, number] | [number, 'auto'];
  chartType?: 'line' | 'area';
  series: ChartSeries[];
  badges?: { label: string; value: string }[];
  delayMs?: number;
}

// Tooltip customizado
function CustomTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2 shadow-soft text-[12px]">
      <p className="mb-1 font-medium text-muted-foreground">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="tabular-nums font-semibold" style={{ color: p.color }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(1) : p.value} {unit}
        </p>
      ))}
      <p className="mt-1 text-[10px] text-muted-foreground italic">dados simulados</p>
    </div>
  );
}

export function HospitalChart({
  title,
  subtitle,
  unit,
  yDomain = [0, 100],
  chartType = 'line',
  series,
  badges,
  delayMs = 0,
}: HospitalChartProps) {
  // Formata data para Recharts: array de { hour, [key]: value }
  const chartData = series[0]?.data.map((pt, i) => {
    const row: Record<string, string | number> = { hour: pt.hour };
    series.forEach((s) => {
      row[s.key] = s.data[i]?.value ?? 0;
    });
    return row;
  }) ?? [];

  const ChartComponent = chartType === 'area' ? AreaChart : LineChart;

  return (
    <div
      className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      {/* Cabeçalho */}
      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Histórico 24h</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{title}</h3>
          {subtitle && <p className="text-[11px] text-muted-foreground">{subtitle}</p>}
        </div>
        {badges && (
          <div className="flex flex-wrap gap-2">
            {badges.map((b) => (
              <span
                key={b.label}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary px-2.5 py-1 text-[11px] font-semibold text-foreground"
              >
                <span className="text-muted-foreground">{b.label}</span>
                {b.value}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Gráfico */}
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ChartComponent data={chartData}>
            <defs>
              {series.map((s) => (
                <linearGradient key={s.key} id={`area-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={s.color} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={s.color} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 6" stroke="hsl(var(--border))" strokeOpacity={0.6} />
            <XAxis
              dataKey="hour"
              tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))', fontFamily: 'Inter, sans-serif' }}
              tickLine={false}
              axisLine={false}
              interval={3}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))', fontFamily: 'Inter, sans-serif' }}
              tickLine={false}
              axisLine={false}
              width={38}
              tickFormatter={(v: number) => `${v}`}
            />
            <Tooltip content={<CustomTooltip unit={unit} />} />

            {series.map((s) =>
              chartType === 'area' ? (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2}
                  fill={`url(#area-${s.key})`}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0, fill: s.color }}
                />
              ) : (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={2.5}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0, fill: s.color }}
                />
              ),
            )}
          </ChartComponent>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
