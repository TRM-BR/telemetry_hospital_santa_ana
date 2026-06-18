import { AlertTriangle, CloudRain, Droplets, Gauge, Radar, Thermometer } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { cn } from '../lib/cn';

const RAIN_VIEWER_SRC =
  'https://www.rainviewer.com/map.html?loc=-23.5373,-46.7453,10.030099623626088&oC=true&oCS=1&c=9&o=83&lm=1&layer=radar&sm=1&sn=1';

const rainSeries = [
  { hour: '08:00', mmh: 0.6 },
  { hour: '09:00', mmh: 1.4 },
  { hour: '10:00', mmh: 3.8 },
  { hour: '11:00', mmh: 7.2 },
  { hour: '12:00', mmh: 12.6 },
  { hour: '13:00', mmh: 9.3 },
  { hour: '14:00', mmh: 5.1 },
  { hour: '15:00', mmh: 2.4 },
];

const weatherSnapshot = {
  riverLevelM: 2.84,
  riverNormalM: 2.4,
  temperatureC: 23.7,
  humidityPct: 82,
  rainNowMmh: 12.6,
  alertAboveNormalPct: 18,
  updatedAt: '18/06/2026 14:35',
};

type Tone = 'primary' | 'info' | 'warning' | 'danger';

const toneClass: Record<Tone, { icon: string; bar: string; border: string }> = {
  primary: {
    icon: 'bg-primary/10 text-primary',
    bar: 'bg-primary',
    border: 'border-primary/20',
  },
  info: {
    icon: 'bg-sky-100 text-sky-700',
    bar: 'bg-sky-600',
    border: 'border-sky-200',
  },
  warning: {
    icon: 'bg-accent/20 text-accent-foreground',
    bar: 'bg-accent',
    border: 'border-accent/40',
  },
  danger: {
    icon: 'bg-destructive/10 text-destructive',
    bar: 'bg-destructive',
    border: 'border-destructive/30',
  },
};

interface MetricCardProps {
  icon: LucideIcon;
  label: string;
  value: string;
  helper: string;
  tone?: Tone;
  progress?: number;
}

function MetricCard({
  icon: Icon,
  label,
  value,
  helper,
  tone = 'primary',
  progress,
}: MetricCardProps) {
  const styles = toneClass[tone];
  const safeProgress = progress === undefined ? undefined : Math.max(0, Math.min(100, progress));

  return (
    <article className={cn('rounded-2xl border bg-card p-5 shadow-soft', styles.border)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-bold tabular-nums text-foreground">{value}</p>
        </div>
        <div className={cn('rounded-xl p-2.5', styles.icon)}>
          <Icon className="h-5 w-5" />
        </div>
      </div>

      <p className="mt-3 min-h-10 text-sm leading-5 text-muted-foreground">{helper}</p>

      {safeProgress !== undefined && (
        <div className="mt-4 h-2 rounded-full bg-secondary">
          <div
            className={cn('h-full rounded-full', styles.bar)}
            style={{ width: `${safeProgress}%` }}
          />
        </div>
      )}
    </article>
  );
}

function AlertCard() {
  return (
    <article className="rounded-2xl border border-destructive/30 bg-card p-5 shadow-soft md:col-span-2 xl:col-span-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Alertas</p>
          <h2 className="mt-2 text-xl font-semibold text-foreground">Nivel do rio em atencao</h2>
        </div>
        <div className="rounded-xl bg-destructive/10 p-2.5 text-destructive">
          <AlertTriangle className="h-5 w-5" />
        </div>
      </div>

      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        Nivel do rio {weatherSnapshot.alertAboveNormalPct}% acima da normalidade. Monitorar pontos
        de acesso ao hospital e manter equipe de manutencao em prontidao.
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        <span className="rounded-full border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive">
          Prioridade media
        </span>
        <span className="rounded-full border border-border bg-secondary/70 px-3 py-1 text-xs font-medium text-muted-foreground">
          Atualizado {weatherSnapshot.updatedAt}
        </span>
      </div>
    </article>
  );
}

function RadarCard() {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
      <div className="flex flex-col gap-3 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Radar de chuva
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-foreground">Monitoramento meteorologico</h1>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-3 py-1.5 text-xs font-semibold text-primary">
          <Radar className="h-3.5 w-3.5" />
          Ao vivo
        </div>
      </div>

      <iframe
        title="Radar meteorologico RainViewer"
        src={RAIN_VIEWER_SRC}
        className="h-[50vh] min-h-[360px] w-full"
        frameBorder="0"
        loading="lazy"
        allowFullScreen
      />
    </section>
  );
}

function RainChartCard() {
  return (
    <article className="rounded-2xl border border-sky-200 bg-card p-5 shadow-soft md:col-span-2 xl:col-span-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Chuva</p>
          <h2 className="mt-1 text-lg font-semibold text-foreground">Intensidade em mm/h</h2>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-700">
          <CloudRain className="h-3.5 w-3.5" />
          {weatherSnapshot.rainNowMmh.toFixed(1)} mm/h agora
        </div>
      </div>

      <div className="mt-5 h-[230px] w-full">
        <ResponsiveContainer>
          <BarChart data={rainSeries} margin={{ top: 10, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 4" vertical={false} />
            <XAxis
              dataKey="hour"
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="hsl(var(--muted-foreground))"
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={44}
              tickFormatter={(value: number) => `${value}`}
            />
            <Tooltip
              cursor={{ fill: 'hsl(var(--secondary))' }}
              contentStyle={{
                background: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: 10,
                boxShadow: 'var(--shadow-soft)',
                fontSize: 12,
              }}
              formatter={(value) => [`${Number(value).toFixed(1)} mm/h`, 'Chuva']}
            />
            <Bar dataKey="mmh" radius={[8, 8, 0, 0]} fill="hsl(200 85% 45%)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

const WeatherDashboard = () => {
  const riverProgress = (weatherSnapshot.riverLevelM / 4) * 100;

  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <div className="flex items-center gap-3 text-primary">
            <CloudRain className="h-5 w-5" />
            <div className="leading-tight">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Hospital Santa Ana
              </p>
              <p className="text-[12px] font-semibold text-foreground">Dashboard de clima</p>
            </div>
          </div>

          <span className="hidden rounded-full border border-border bg-secondary/70 px-3 py-1.5 text-xs font-medium text-muted-foreground sm:inline-flex">
            Dados mockados
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-8 sm:py-8">
        <RadarCard />

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <AlertCard />

          <MetricCard
            icon={Gauge}
            label="Nivel do rio"
            value={`${weatherSnapshot.riverLevelM.toFixed(2)} m`}
            helper={`Referencia normal ate ${weatherSnapshot.riverNormalM.toFixed(2)} m.`}
            tone="danger"
            progress={riverProgress}
          />

          <MetricCard
            icon={Thermometer}
            label="Temperatura"
            value={`${weatherSnapshot.temperatureC.toFixed(1)}\u00b0C`}
            helper="Leitura ambiente proxima ao hospital."
            tone="warning"
            progress={weatherSnapshot.temperatureC * 2.2}
          />

          <RainChartCard />

          <MetricCard
            icon={Droplets}
            label="Umidade"
            value={`${weatherSnapshot.humidityPct}%`}
            helper="Umidade relativa do ar na ultima leitura."
            tone="info"
            progress={weatherSnapshot.humidityPct}
          />
        </section>

        <p className="px-1 text-[11px] text-muted-foreground">
          Atualizado {weatherSnapshot.updatedAt} - leituras simuladas para validacao visual.
        </p>
      </main>
    </div>
  );
};

export default WeatherDashboard;
