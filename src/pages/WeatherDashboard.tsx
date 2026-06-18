import { AlertCircle, AlertTriangle, Check, ChevronRight, CloudRain, Info, Radar } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import HistoryChart from '../components/dashboard/HistoryChart';
import { cn } from '../lib/cn';
import type { SeriesPoint } from '../types/telemetry';

const RAIN_VIEWER_SRC =
  'https://www.rainviewer.com/map.html?loc=-23.5373,-46.7453,10.030099623626088&oC=true&oCS=1&c=9&o=83&lm=1&layer=radar&sm=1&sn=1';

const BASE_TIME = new Date('2026-06-17T15:00:00-03:00').getTime();
const HOUR_MS = 60 * 60 * 1000;
const CHART_HEIGHT_CLASS = 'h-[300px]';

function series(values: number[]): SeriesPoint[] {
  return values.map((v, index) => ({
    t: BASE_TIME + index * HOUR_MS,
    v,
  }));
}

const riverLevelSeries = series([
  2.18, 2.17, 2.19, 2.2, 2.22, 2.25, 2.27, 2.26,
  2.28, 2.31, 2.34, 2.4, 2.49, 2.61, 2.72, 2.84,
  2.9, 2.87, 2.81, 2.76, 2.73, 2.75, 2.79, 2.84,
]);
const rainSeries = series([
  0, 0.2, 0, 0, 0.4, 1.1, 0.6, 0,
  0, 0.2, 1.8, 4.6, 8.9, 13.2, 10.8, 6.4,
  3.1, 1.2, 0.4, 0, 0, 0.3, 1.5, 2.2,
]);
const temperatureSeries = series([
  24.6, 24.1, 23.5, 22.8, 22.2, 21.7, 21.4, 21.1,
  20.9, 21.3, 22.4, 23.5, 24.2, 24.8, 24.4, 23.7,
  23.1, 22.6, 22.3, 22, 21.8, 22.1, 22.8, 23.7,
]);
const humiditySeries = series([
  72, 74, 76, 78, 80, 82, 83, 85,
  86, 84, 81, 79, 82, 88, 91, 89,
  86, 84, 82, 80, 79, 80, 81, 82,
]);

const weatherSnapshot = {
  riverLevelM: 2.84,
  riverNormalM: 2.4,
  temperatureC: 23.7,
  humidityPct: 82,
  rainNowMmh: 12.6,
  alertAboveNormalPct: 18,
  updatedAt: new Date('2026-06-18T14:35:00-03:00'),
};

type WeatherAlertSeverity = 'moderado' | 'alto' | 'critico';

interface WeatherAlert {
  id: string;
  title: string;
  description: string;
  severity: WeatherAlertSeverity;
  date: Date;
  viewed?: boolean;
}

const weatherAlerts: WeatherAlert[] = [
  {
    id: 'MET-001',
    title: 'Nivel do rio acima do normal',
    description: `Rio ${weatherSnapshot.alertAboveNormalPct}% acima da referencia operacional.`,
    severity: 'alto',
    date: new Date('2026-06-18T14:35:00-03:00'),
  },
  {
    id: 'MET-002',
    title: 'Chuva moderada nas proximidades',
    description: 'Intensidade atual exige acompanhamento do acumulado horario.',
    severity: 'moderado',
    date: new Date('2026-06-18T13:10:00-03:00'),
    viewed: true,
  },
];

function formatOccurrence(date: Date): string {
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function severityIcon(severity: WeatherAlertSeverity) {
  if (severity === 'critico') return AlertCircle;
  if (severity === 'alto') return AlertCircle;
  return AlertTriangle;
}

function severityBorderColor(severity: WeatherAlertSeverity): string {
  if (severity === 'critico') return 'border-l-red-600';
  if (severity === 'alto') return 'border-l-red-400';
  return 'border-l-orange-400';
}

function severityIconColor(severity: WeatherAlertSeverity): string {
  if (severity === 'critico') return 'text-red-600';
  if (severity === 'alto') return 'text-red-400';
  return 'text-orange-500';
}

function severityBgTint(severity: WeatherAlertSeverity): string {
  if (severity === 'critico') return 'bg-red-600/10';
  if (severity === 'alto') return 'bg-red-400/10';
  return 'bg-orange-500/10';
}

function WeatherAlertsCard({ delayMs = 0 }: { delayMs?: number }) {
  const navigate = useNavigate();

  return (
    <div
      className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in flex flex-col"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-foreground">Avisos</h3>
          {weatherAlerts.length > 0 && (
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
              {weatherAlerts.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => navigate('/alertas')}
          className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Ver todos
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="space-y-2.5 max-h-[280px] overflow-y-auto">
        {weatherAlerts.map((alert) => {
          const Icon = severityIcon(alert.severity);
          return (
            <div
              key={alert.id}
              className={cn(
                'flex items-start gap-3 rounded-xl px-4 py-3 border-l-[3px] hover:opacity-90 transition-opacity',
                severityBgTint(alert.severity),
                severityBorderColor(alert.severity),
                alert.viewed && 'opacity-80',
              )}
            >
              <Icon className={cn('mt-0.5 h-[18px] w-[18px] flex-shrink-0', severityIconColor(alert.severity))} />

              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground leading-tight line-clamp-2">
                  {alert.title}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                  {alert.description}
                </p>
                <p className="text-[11px] text-muted-foreground/70 mt-1 tabular-nums">
                  {formatOccurrence(alert.date)}
                </p>
              </div>

              <button
                type="button"
                title={alert.viewed ? 'Marcado como visto' : 'Marcar como visto'}
                className={cn(
                  'flex-shrink-0 h-6 w-6 rounded-full flex items-center justify-center transition-all',
                  alert.viewed
                    ? 'bg-emerald-500 text-white shadow-sm'
                    : 'text-foreground/30 hover:text-foreground/60 hover:bg-muted/60',
                )}
              >
                <Check className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function RadarCard() {
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft animate-drop-in">
      <div className="flex flex-col gap-3 border-b border-border p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Radar de chuva
          </p>
          <h1 className="mt-1 text-lg font-semibold text-foreground">Monitoramento meteorologico</h1>
        </div>
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-foreground tabular-nums">
          <Radar className="h-3.5 w-3.5 text-primary" />
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

const WeatherDashboard = () => {
  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 sm:px-8 min-h-[104px]">
          <div className="flex items-center gap-3 text-primary">
            <CloudRain className="h-6 w-6" />
            <div className="leading-tight">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Hospital Santa Ana
              </p>
              <p className="mt-0.5 text-2xl font-bold text-foreground">Dashboard meteorologico</p>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Status</span>
            <span className="inline-flex items-center gap-1 rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-foreground">
              <Info className="h-3.5 w-3.5 text-primary" />
              Dados mockados
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6 sm:px-8 sm:py-8">
        <RadarCard />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <WeatherAlertsCard delayMs={0} />
          <HistoryChart
            title="Historico de Nivel do Rio"
            unit="m"
            windowKey="24h"
            yDomain="smart"
            chartHeightClass={CHART_HEIGHT_CLASS}
            yAxisWidth={52}
            badges={[
              { label: 'Nivel', value: `${weatherSnapshot.riverLevelM.toFixed(2)} m` },
            ]}
            referenceLines={[
              {
                value: weatherSnapshot.riverNormalM,
                label: 'Normal',
                color: 'hsl(var(--accent))',
              },
            ]}
            series={[
              {
                key: 'river',
                label: 'Nivel',
                color: 'var(--primary)',
                data: riverLevelSeries,
              },
            ]}
            delayMs={80}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <HistoryChart
            title="Historico de Chuva"
            unit="mm/h"
            windowKey="24h"
            yDomain={[0, 'auto']}
            lineType="monotone"
            chartHeightClass={CHART_HEIGHT_CLASS}
            yAxisWidth={52}
            tooltipNote="intensidade de chuva por hora"
            badges={[
              { label: 'Chuva', value: `${weatherSnapshot.rainNowMmh.toFixed(2)} mm/h` },
            ]}
            series={[
              {
                key: 'rain',
                label: 'Chuva',
                color: 'var(--primary)',
                data: rainSeries,
              },
            ]}
            delayMs={160}
          />
          <HistoryChart
            title="Historico de Temperatura"
            unit="C"
            windowKey="24h"
            yDomain="smart"
            chartHeightClass={CHART_HEIGHT_CLASS}
            yAxisWidth={52}
            badges={[
              { label: 'Temperatura', value: `${weatherSnapshot.temperatureC.toFixed(1)} C` },
            ]}
            series={[
              {
                key: 'temperature',
                label: 'Temperatura',
                color: 'var(--primary)',
                data: temperatureSeries,
              },
            ]}
            delayMs={240}
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <HistoryChart
            title="Historico de Umidade"
            unit="%"
            windowKey="24h"
            yDomain={[0, 100]}
            chartHeightClass={CHART_HEIGHT_CLASS}
            yAxisWidth={52}
            badges={[
              { label: 'Umidade', value: `${weatherSnapshot.humidityPct}%` },
            ]}
            series={[
              {
                key: 'humidity',
                label: 'Umidade',
                color: 'var(--primary)',
                data: humiditySeries,
              },
            ]}
            delayMs={320}
          />
        </div>

        <p className="text-[11px] text-muted-foreground">
          Janela 24h - dados mockados - atualizado com sucesso -{' '}
          <span className="tabular-nums">
            {weatherSnapshot.updatedAt.toLocaleTimeString('pt-BR')}
          </span>
        </p>
      </main>
    </div>
  );
};

export default WeatherDashboard;
