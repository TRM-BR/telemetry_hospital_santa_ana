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

function gsmLabel(dbm: number | null): string {
  if (dbm === null) return 'Sem sinal';
  if (dbm < -110) return 'Muito fraco';
  if (dbm < -90)  return 'Fraco';
  if (dbm < -70)  return 'Bom';
  return 'Excelente';
}

function gsmHintTone(dbm: number | null): 'default' | 'accent' | 'danger' {
  if (dbm === null || dbm < -90) return 'danger';
  return 'default';
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

function KpiSkeleton({ featured }: { featured?: boolean }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="flex items-start justify-between">
        <div className="space-y-2.5">
          <Skeleton className="h-2.5 w-16" />
          <Skeleton className={cn('w-28', featured ? 'h-11' : 'h-9')} />
        </div>
        <Skeleton className="h-10 w-10 rounded-xl" />
      </div>
      <Skeleton className="mt-4 h-7 w-full rounded" />
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-3">
      {children}
    </p>
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

  // Spark helpers — last 30 points of each series (display only, no calculation)
  const spark = (col: string): number[] =>
    (series[col] ?? []).slice(-30).map((p: EnergySeriesPoint) => p.v);

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
  const muted = data ? !data.online : false;

  const hasPower   = powerSeries.some((s) => s.data.length > 0);
  const hasVoltage = voltageSeries.some((s) => s.data.length > 0);
  const hasCurrent = currentSeries[0].data.length > 0;
  const hasPf      = pfSeries[0].data.length > 0;
  const hasAccum   = accumSeries.some((s) => s.data.length > 0);

  const gsm = latest?.gsm_signal_rssi_dbm ?? null;

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

          <div className="flex flex-col items-center gap-0.5">
            <div className="flex items-center gap-2 text-primary">
              <Zap className="h-4 w-4" />
              <span className="text-sm font-semibold text-foreground">
                {data?.installation_name ?? 'Energia'}
              </span>
              {data && (
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                    data.online
                      ? 'bg-emerald-500/15 text-emerald-500'
                      : 'bg-destructive/15 text-destructive',
                  )}
                >
                  {data.online && (
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    </span>
                  )}
                  {data.online ? 'online' : 'offline'}
                </span>
              )}
            </div>
            <span className="text-[10px] text-muted-foreground">Medidor SM-3EGW · atualiza a cada {AUTO_REFRESH_MS / 1000}s</span>
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

        {/* ── Seção 1: Indicadores principais ────────────────────────────── */}
        <section>
          <SectionLabel>Indicadores principais</SectionLabel>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <KpiSkeleton key={i} featured />)
            ) : (
              <>
                <KpiCard
                  icon={Zap}
                  label="Potência ativa"
                  value={latest?.active_power_total_w ?? 0}
                  suffix="W"
                  decimals={1}
                  tone={(latest?.active_power_total_w ?? 0) < 0 ? 'accent' : 'default'}
                  spark={spark('active_power_total_w')}
                  featured
                  delayMs={0}
                />
                <KpiCard
                  icon={Activity}
                  label="Potência reativa"
                  value={latest?.reactive_power_total_var ?? 0}
                  suffix="VAr"
                  decimals={1}
                  spark={spark('reactive_power_total_var')}
                  featured
                  delayMs={50}
                />
                <KpiCard
                  icon={Gauge}
                  label="Tensão média"
                  value={latest?.voltage_avg_v ?? 0}
                  suffix="V"
                  decimals={1}
                  spark={spark('voltage_phase_a_v')}
                  featured
                  delayMs={100}
                />
                <KpiCard
                  icon={Activity}
                  label="Corrente total"
                  value={latest?.current_total_a ?? 0}
                  suffix="A"
                  decimals={2}
                  spark={spark('current_total_a')}
                  featured
                  delayMs={150}
                />
              </>
            )}
          </div>
        </section>

        {/* ── Seção 2: Qualidade e contexto ──────────────────────────────── */}
        <section>
          <SectionLabel>Qualidade e contexto</SectionLabel>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <KpiSkeleton key={i} />)
            ) : (
              <>
                <KpiCard
                  icon={Gauge}
                  label="Fator de potência"
                  value={latest?.power_factor_total ?? 0}
                  decimals={3}
                  spark={spark('power_factor_total')}
                  delayMs={0}
                />
                <KpiCard
                  icon={TrendingDown}
                  label="Consumo acumulado"
                  value={latest?.active_energy_consumed_total_kwh ?? 0}
                  suffix="kWh"
                  decimals={3}
                  tone="danger"
                  delayMs={50}
                />
                <KpiCard
                  icon={TrendingUp}
                  label="Geração acumulada"
                  value={latest?.active_energy_generated_total_kwh ?? 0}
                  suffix="kWh"
                  decimals={3}
                  delayMs={100}
                />
                <KpiCard
                  icon={Signal}
                  label="Sinal GSM"
                  value={gsm ?? 0}
                  suffix="dBm"
                  decimals={0}
                  tone={gsm === null || gsm < -90 ? 'danger' : 'default'}
                  hint={gsmLabel(gsm)}
                  hintTone={gsmHintTone(gsm)}
                  delayMs={150}
                />
              </>
            )}
          </div>
        </section>

        {/* ── Balanço energético (full width) ────────────────────────────── */}
        {!isLoading && (
          <EnergyBalanceChart
            bars={bars}
            windowKey={windowKey}
            muted={muted}
            lastSeenUtc={data?.last_seen_utc}
            delayMs={100}
            chartHeightClass={CHART_HEIGHT}
          />
        )}

        {/* ── Potência + Tensão (2 colunas) ──────────────────────────────── */}
        {!isLoading && (hasPower || hasVoltage) && (
          <div className="grid gap-4 lg:grid-cols-2">
            {hasPower && (
              <HistoryChart
                title="Potência"
                unit="W"
                series={powerSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={150}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
              />
            )}
            {hasVoltage && (
              <HistoryChart
                title="Tensão por fase"
                unit="V"
                series={voltageSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={200}
                yDomain="robust"
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
              />
            )}
          </div>
        )}

        {/* ── Corrente + FP (2 colunas) ──────────────────────────────────── */}
        {!isLoading && (hasCurrent || hasPf) && (
          <div className="grid gap-4 lg:grid-cols-2">
            {hasCurrent && (
              <HistoryChart
                title="Corrente total"
                unit="A"
                series={currentSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={250}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
              />
            )}
            {hasPf && (
              <HistoryChart
                title="Fator de potência"
                unit=""
                series={pfSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={300}
                yDomain={[0, 1]}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
              />
            )}
          </div>
        )}

        {/* ── Energia acumulada (full width) ─────────────────────────────── */}
        {!isLoading && hasAccum && (
          <HistoryChart
            title="Energia acumulada"
            unit="kWh"
            series={accumSeries}
            windowKey={wk}
            chartHeightClass={CHART_HEIGHT}
            delayMs={350}
            muted={muted}
            lastSeenUtc={data?.last_seen_utc}
          />
        )}

        {/* Estado vazio */}
        {!isLoading && !error && bars.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center shadow-soft">
            <Battery className="mx-auto h-8 w-8 text-muted-foreground/60" />
            <h3 className="mt-3 text-base font-semibold text-foreground">Sem medições no período</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Aguardando dados do medidor SM-3EGW. Verifique a conexão MQTT e o parse_worker.
            </p>
          </div>
        )}

        {/* Rodapé */}
        {data?.last_seen_utc && (
          <p className="pb-4 text-center text-[11px] text-muted-foreground">
            Última leitura:{' '}
            <span className="tabular-nums text-foreground/70">
              {fmtLastSeen(data.last_seen_utc)}
            </span>
          </p>
        )}
      </main>
    </div>
  );
}
