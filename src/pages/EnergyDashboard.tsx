import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Zap, Activity, Gauge, Battery,
  TrendingDown, TrendingUp, Signal, WifiOff,
} from 'lucide-react';
import { useEnergyDashboard } from '../hooks/useEnergyDashboard';
import { EnergyBalanceChart } from '../components/energy/EnergyBalanceChart';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { KpiCard } from '../components/dashboard/KpiCard';
import { Skeleton } from '../components/ui/Skeleton';
import { cn } from '../lib/cn';
import { TOP_BAR_HEIGHT_PX } from '../constants/layout';
import type { EnergyWindowKey, EnergySeriesPoint } from '../types/energy';
import { ENERGY_WINDOW_OPTIONS, ENERGY_WINDOW_TO_HOURS } from '../types/energy';
import type { WindowKey } from '../types/telemetry';

const AUTO_REFRESH_MS = 30_000;
const CHART_HEIGHT = 'h-[260px]';

function fmtLastSeen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}


function toChartSeries(
  pts: EnergySeriesPoint[] | undefined,
  key: string,
  label: string,
  color: string,
): ChartSeries {
  return {
    key,
    label,
    color,
    data: (pts ?? []).map((p) => ({ t: p.t, v: p.v })),
  };
}

function WindowSelector({
  value,
  onChange,
}: {
  value: EnergyWindowKey;
  onChange: (k: EnergyWindowKey) => void;
}) {
  return (
    <div className="flex items-center gap-1 rounded-xl border border-border bg-secondary p-1">
      {ENERGY_WINDOW_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            value === opt.value
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function OfflineBanner({ lastSeen }: { lastSeen: string | null }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      <WifiOff className="h-4 w-4 flex-shrink-0" />
      <span>
        Medidor offline · último dado:{' '}
        <span className="font-medium tabular-nums">{fmtLastSeen(lastSeen)}</span>
      </span>
    </div>
  );
}

function KpiSkeleton() {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="space-y-3">
        <Skeleton className="h-2.5 w-16" />
        <Skeleton className="h-9 w-28" />
      </div>
    </div>
  );
}

export default function EnergyDashboard() {
  const { slug = 'escola' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [windowKey, setWindowKey] = useState<EnergyWindowKey>('24h');

  const hours = ENERGY_WINDOW_TO_HOURS[windowKey];
  const { data, isLoading, error } = useEnergyDashboard(slug, hours);

  const latest = data?.latest;
  const series = data?.series ?? {};
  const bars   = data?.bars   ?? [];

  // ── Séries para HistoryChart ─────────────────────────────────────────────

  const powerSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.active_power_total_w,    'pt', 'Potência ativa',    'var(--primary)'),
    toChartSeries(series.reactive_power_total_var, 'qt', 'Potência reativa',  'var(--accent)'),
  ], [series]);

  const voltageSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.voltage_phase_a_v, 'ua', 'Fase A', '217 91% 60%'),
    toChartSeries(series.voltage_phase_b_v, 'ub', 'Fase B', '142 71% 45%'),
    toChartSeries(series.voltage_phase_c_v, 'uc', 'Fase C', '38 92% 50%'),
  ], [series]);

  const currentSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.current_total_a, 'it', 'Corrente total', 'var(--primary)'),
  ], [series]);

  const pfSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.power_factor_total, 'pf', 'Fator de potência', 'var(--accent)'),
  ], [series]);

  const accumSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.active_energy_consumed_total_kwh,     'eptc', 'Consumo acumulado',  'hsl(var(--destructive))'),
    toChartSeries(series.active_energy_generated_total_kwh,    'eptg', 'Geração acumulada',  'hsl(var(--primary))'),
    toChartSeries(series.reactive_energy_generated_total_kvarh,'eqtg', 'Geração reativa',    '262 83% 58%'),
  ], [series]);

  const wk = windowKey as unknown as WindowKey;

  // ── Média das três fases para KPI de tensão ──────────────────────────────
  const voltageAvg = useMemo(() => {
    const vals = [latest?.voltage_phase_a_v, latest?.voltage_phase_b_v, latest?.voltage_phase_c_v]
      .filter((v): v is number => v !== null && v !== undefined);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }, [latest]);

  return (
    <div className="min-h-screen w-full bg-secondary">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div
          className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-5 sm:px-8"
          style={{ minHeight: TOP_BAR_HEIGHT_PX }}
        >
          <button
            type="button"
            onClick={() => navigate(`/instalacao/${slug}`)}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar
          </button>

          <div className="flex items-center gap-2 text-primary">
            <Zap className="h-4 w-4" />
            <span className="text-sm font-semibold text-foreground">
              {data?.installation_name ?? 'Energia'}
            </span>
            {data && (
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                  data.online
                    ? 'bg-emerald-500/15 text-emerald-500'
                    : 'bg-destructive/15 text-destructive',
                )}
              >
                {data.online ? 'online' : 'offline'}
              </span>
            )}
          </div>

          <WindowSelector value={windowKey} onChange={setWindowKey} />
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-5 py-8 sm:px-8">
        {/* Erro */}
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            Não foi possível carregar os dados. Verifique a conexão e tente novamente.
          </div>
        )}

        {/* Offline banner */}
        {!isLoading && data && !data.online && (
          <OfflineBanner lastSeen={data.last_seen_utc} />
        )}

        {/* KPI cards */}
        <section className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {isLoading ? (
            Array.from({ length: 8 }).map((_, i) => <KpiSkeleton key={i} />)
          ) : (
            <>
              <KpiCard
                icon={Zap}
                label="Potência ativa"
                value={latest?.active_power_total_w ?? 0}
                suffix="W"
                decimals={1}
                tone={
                  (latest?.active_power_total_w ?? 0) < 0 ? 'accent' : 'default'
                }
                delayMs={0}
              />
              <KpiCard
                icon={Activity}
                label="Potência reativa"
                value={latest?.reactive_power_total_var ?? 0}
                suffix="VAr"
                decimals={1}
                delayMs={50}
              />
              <KpiCard
                icon={Gauge}
                label="Tensão média"
                value={voltageAvg ?? 0}
                suffix="V"
                decimals={1}
                delayMs={100}
              />
              <KpiCard
                icon={Activity}
                label="Corrente total"
                value={latest?.current_total_a ?? 0}
                suffix="A"
                decimals={2}
                delayMs={150}
              />
              <KpiCard
                icon={Gauge}
                label="Fator de potência"
                value={latest?.power_factor_total ?? 0}
                decimals={3}
                delayMs={200}
              />
              <KpiCard
                icon={TrendingDown}
                label="Consumo acumulado"
                value={latest?.active_energy_consumed_total_kwh ?? 0}
                suffix="kWh"
                decimals={3}
                tone="danger"
                delayMs={250}
              />
              <KpiCard
                icon={TrendingUp}
                label="Geração acumulada"
                value={latest?.active_energy_generated_total_kwh ?? 0}
                suffix="kWh"
                tone="accent"
                decimals={3}
                delayMs={300}
              />
              <KpiCard
                icon={Signal}
                label="Sinal GSM"
                value={latest?.gsm_signal_rssi_dbm ?? 0}
                suffix="dBm"
                decimals={0}
                tone={
                  latest?.gsm_signal_rssi_dbm === null
                    ? 'danger'
                    : (latest?.gsm_signal_rssi_dbm ?? 0) < -90
                      ? 'danger'
                      : 'default'
                }
                delayMs={350}
              />
            </>
          )}
        </section>

        {/* Gráfico de barras divergente */}
        {!isLoading && (
          <EnergyBalanceChart
            bars={bars}
            windowKey={windowKey}
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
            delayMs={100}
            chartHeightClass={CHART_HEIGHT}
          />
        )}

        {/* Linha — potência ativa + reativa */}
        {!isLoading && powerSeries.some((s) => s.data.length > 0) && (
          <HistoryChart
            title="Potência"
            unit="W"
            series={powerSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={150}
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Linha — tensões por fase */}
        {!isLoading && voltageSeries.some((s) => s.data.length > 0) && (
          <HistoryChart
            title="Tensão por fase"
            unit="V"
            series={voltageSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={200}
            yDomain="robust"
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Linha — corrente total */}
        {!isLoading && currentSeries[0].data.length > 0 && (
          <HistoryChart
            title="Corrente total"
            unit="A"
            series={currentSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={250}
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Linha — fator de potência */}
        {!isLoading && pfSeries[0].data.length > 0 && (
          <HistoryChart
            title="Fator de potência"
            unit=""
            series={pfSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={300}
            yDomain={[0, 1]}
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Linha — energia acumulada */}
        {!isLoading && accumSeries.some((s) => s.data.length > 0) && (
          <HistoryChart
            title="Energia acumulada"
            unit="kWh"
            series={accumSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={350}
            muted={data ? !data.online : false}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Estado vazio — sem medições */}
        {!isLoading && !error && bars.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center shadow-soft">
            <Battery className="mx-auto h-8 w-8 text-muted-foreground/60" />
            <h3 className="mt-3 text-base font-semibold text-foreground">Sem medições no período</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Aguardando dados do medidor SM-3EGW. Verifique a conexão MQTT e o parse_worker.
            </p>
          </div>
        )}

        {/* Rodapé — última atualização */}
        {data?.last_seen_utc && (
          <p className="pb-4 text-center text-[11px] text-muted-foreground">
            Última leitura:{' '}
            <span className="tabular-nums text-foreground/70">
              {fmtLastSeen(data.last_seen_utc)}
            </span>
            {' · '}
            Atualiza a cada {AUTO_REFRESH_MS / 1000}s
          </p>
        )}
      </main>
    </div>
  );
}
