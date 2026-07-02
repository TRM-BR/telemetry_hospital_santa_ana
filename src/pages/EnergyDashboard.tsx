import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Zap, Activity, Gauge, Battery,
  TrendingDown, TrendingUp, Signal, WifiOff, RefreshCw,
} from 'lucide-react';
import { useEnergyDashboard } from '../hooks/useEnergyDashboard';
import { EnergyBalanceChart } from '../components/energy/EnergyBalanceChart';
import { EnergyKpiCard } from '../components/energy/EnergyKpiCard';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { Skeleton } from '../components/ui/Skeleton';
import { cn } from '../lib/cn';
import { TOP_BAR_HEIGHT_PX } from '../constants/layout';
import type { EnergyWindowKey, EnergySeriesPoint } from '../types/energy';
import { ENERGY_WINDOW_OPTIONS, ENERGY_WINDOW_TO_HOURS } from '../types/energy';
import type { WindowKey } from '../types/telemetry';

const AUTO_REFRESH_MS = 30_000;
const CHART_HEIGHT = 'h-[240px]';

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

function gsmTone(dbm: number | null): 'default' | 'danger' {
  return dbm === null || dbm < -90 ? 'danger' : 'default';
}

function pfTone(pf: number | null): 'default' | 'danger' {
  return pf !== null && pf < 0.92 ? 'danger' : 'default';
}

// ── Window selector (v0 style) ─────────────────────────────────────────────

function WindowSelector({
  value,
  onChange,
}: {
  value: EnergyWindowKey;
  onChange: (k: EnergyWindowKey) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Janela temporal"
      className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5 shadow-sm"
    >
      {ENERGY_WINDOW_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          aria-pressed={value === opt.value}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            value === opt.value
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground',
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ── Offline banner ─────────────────────────────────────────────────────────

function OfflineBanner({ lastSeen }: { lastSeen: string | null }) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
      <WifiOff className="h-4 w-4 shrink-0" />
      <span>
        Medidor offline · último dado:{' '}
        <span className="font-medium tabular-nums">{fmtLastSeen(lastSeen)}</span>
      </span>
    </div>
  );
}

// ── Section heading ────────────────────────────────────────────────────────

function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2
      id={id}
      className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
    >
      {children}
    </h2>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <main className="mx-auto max-w-7xl space-y-8 px-5 py-6 sm:px-8">
      <div className="space-y-3">
        <Skeleton className="h-3 w-40" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-[164px] animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <Skeleton className="h-3 w-44" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-[108px] animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      </div>
      <div className="space-y-4">
        <Skeleton className="h-3 w-36" />
        <div className="h-[380px] animate-pulse rounded-xl border border-border bg-card" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[280px] animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      </div>
    </main>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function EnergyDashboard() {
  const { slug = 'escola' } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [windowKey, setWindowKey] = useState<EnergyWindowKey>('24h');

  const hours = ENERGY_WINDOW_TO_HOURS[windowKey];
  const { data, isLoading, error } = useEnergyDashboard(slug, hours);

  const latest = data?.latest;
  const series = data?.series ?? {};
  const bars   = data?.bars   ?? [];

  const spark = (col: string): number[] =>
    (series[col] ?? []).slice(-30).map((p: EnergySeriesPoint) => p.v);

  const powerSeries = useMemo<ChartSeries[]>(() => [
    toChartSeries(series.active_power_total_w, 'pt', 'Potência ativa', 'var(--primary)'),
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
    toChartSeries(series.active_energy_consumed_total_kwh,  'eptc', 'Consumo acumulado', 'hsl(var(--destructive))'),
    toChartSeries(series.active_energy_generated_total_kwh, 'eptg', 'Geração acumulada', 'hsl(var(--primary))'),
  ], [series]);

  const wk    = windowKey as unknown as WindowKey;
  const muted = data ? !data.online : false;

  const hasPower   = powerSeries.some((s) => s.data.length > 0);
  const hasVoltage = voltageSeries.some((s) => s.data.length > 0);
  const hasCurrent = currentSeries[0].data.length > 0;
  const hasPf      = pfSeries[0].data.length > 0;
  const hasAccum   = accumSeries.some((s) => s.data.length > 0);

  const gsm  = latest?.gsm_signal_rssi_dbm ?? null;
  const pf   = latest?.power_factor_total  ?? null;
  const pActRaw = latest?.active_power_total_w ?? null;
  const pAct = pActRaw ?? 0;

  const FLOW_EPSILON_W = 1;
  const flowHint = pActRaw === null
    ? undefined
    : Math.abs(pActRaw) < FLOW_EPSILON_W
    ? 'Sem fluxo'
    : pActRaw > 0
    ? 'Injetando'
    : 'Consumindo';
  const flowTone = pActRaw === null || Math.abs(pActRaw) < FLOW_EPSILON_W
    ? 'default'
    : pActRaw > 0
    ? 'primary'
    : 'default';

  return (
    <div className="min-h-screen w-full bg-secondary">
      {/* ── Header v0 ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div
          className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-2 sm:px-8 md:flex-row md:items-center md:justify-between"
          style={{ minHeight: TOP_BAR_HEIGHT_PX }}
        >
          {/* Left */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate(`/instalacao/${slug}`)}
              aria-label="Voltar"
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>

            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Zap className="size-5" />
            </span>

            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">
                  Monitoramento energético · Medidor SM-3EGW
                </h1>
                {data && (
                  <span
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.7rem] font-semibold uppercase tracking-wide',
                      data.online
                        ? 'bg-emerald-500/10 text-emerald-500'
                        : 'bg-destructive/10 text-destructive',
                    )}
                  >
                    {data.online ? (
                      <span className="relative flex size-1.5">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex size-1.5 rounded-full bg-emerald-500" />
                      </span>
                    ) : (
                      <span className="size-1.5 rounded-full bg-destructive" />
                    )}
                    {data.online ? 'Online' : 'Offline'}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
              <RefreshCw className="size-3.5" />
              Atualiza a cada {AUTO_REFRESH_MS / 1000}s
            </span>
            <WindowSelector value={windowKey} onChange={setWindowKey} />
          </div>
        </div>
      </header>

      {/* ── Main ──────────────────────────────────────────────────────────── */}
      {isLoading ? (
        <DashboardSkeleton />
      ) : (
        <main className="mx-auto max-w-7xl space-y-8 px-5 py-6 sm:px-8">
          {/* Erro */}
          {error && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              Não foi possível carregar os dados. Verifique a conexão e tente novamente.
            </div>
          )}

          {/* Offline banner */}
          {data && !data.online && (
            <OfflineBanner lastSeen={data.last_seen_utc} />
          )}

          {/* ── Indicadores principais (5 featured) ─────────────────────── */}
          <section aria-labelledby="kpis-principais" className="space-y-3">
            <SectionHeading id="kpis-principais">Indicadores principais</SectionHeading>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              <EnergyKpiCard
                featured
                label="Potência ativa"
                value={pAct}
                unit="W"
                decimals={1}
                icon={Zap}
                tone="primary"
                hint={flowHint}
                hintTone={flowTone}
                spark={spark('active_power_total_w')}
                muted={muted}
                delayMs={0}
              />
              <EnergyKpiCard
                featured
                label="Tensão média"
                value={latest?.voltage_avg_v ?? 0}
                unit="V"
                decimals={1}
                icon={Gauge}
                tone="default"
                spark={spark('voltage_phase_a_v')}
                muted={muted}
                delayMs={60}
              />
              <EnergyKpiCard
                featured
                label="Corrente total"
                value={latest?.current_total_a ?? 0}
                unit="A"
                decimals={2}
                icon={Activity}
                tone="default"
                spark={spark('current_total_a')}
                muted={muted}
                delayMs={120}
              />
              <EnergyKpiCard
                featured
                label="Consumo acumulado"
                value={latest?.active_energy_consumed_total_kwh ?? 0}
                unit="kWh"
                decimals={3}
                icon={TrendingDown}
                tone="danger"
                spark={spark('active_energy_consumed_total_kwh')}
                muted={muted}
                delayMs={180}
              />
              <EnergyKpiCard
                featured
                label="Geração acumulada"
                value={latest?.active_energy_generated_total_kwh ?? 0}
                unit="kWh"
                decimals={3}
                icon={TrendingUp}
                tone="primary"
                spark={spark('active_energy_generated_total_kwh')}
                muted={muted}
                delayMs={240}
              />
            </div>
          </section>

          {/* ── Qualidade e contexto (2 cartões) ────────────────────────── */}
          <section aria-labelledby="kpis-secundarios" className="space-y-3">
            <SectionHeading id="kpis-secundarios">Qualidade e contexto</SectionHeading>
            <div className="grid grid-cols-2 gap-4">
              <EnergyKpiCard
                label="Fator de potência"
                value={pf ?? 0}
                decimals={3}
                icon={Gauge}
                tone={pfTone(pf)}
                hint={pf !== null ? (pf < 0.92 ? 'Abaixo do ideal' : 'Dentro do esperado') : undefined}
                hintTone={pfTone(pf)}
                spark={spark('power_factor_total')}
                muted={muted}
                delayMs={60}
              />
              <EnergyKpiCard
                label="Sinal GSM"
                value={gsm ?? 0}
                unit="dBm"
                decimals={0}
                icon={Signal}
                tone={gsmTone(gsm)}
                hint={gsmLabel(gsm)}
                hintTone={gsmTone(gsm)}
                muted={muted}
                delayMs={120}
              />
            </div>
          </section>

          {/* ── Análise temporal ─────────────────────────────────────────── */}
          <section aria-labelledby="analise" className="space-y-4">
            <SectionHeading id="analise">Análise temporal</SectionHeading>

            {/* Balanço full-width */}
            <EnergyBalanceChart
              bars={bars}
              windowKey={windowKey}
              muted={muted}
              lastSeenUtc={data?.last_seen_utc}
              delayMs={0}
            />

            {/* Potência + Tensão */}
            <div className="grid gap-4 lg:grid-cols-2">
              <HistoryChart
                title="Potência"
                unit="W"
                series={powerSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={60}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
                variant="flat"
                fillMode="line"
              />
              <HistoryChart
                title="Tensão por fase"
                unit="V"
                series={voltageSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={120}
                yDomain="robust"
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
                variant="flat"
                fillMode="line"
              />
            </div>

            {/* Corrente + FP */}
            <div className="grid gap-4 lg:grid-cols-2">
              <HistoryChart
                title="Corrente total"
                unit="A"
                series={currentSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={180}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
                variant="flat"
                fillMode="line"
              />
              <HistoryChart
                title="Fator de potência"
                unit=""
                series={pfSeries}
                windowKey={wk}
                chartHeightClass={CHART_HEIGHT}
                delayMs={240}
                yDomain={[0, 1]}
                muted={muted}
                lastSeenUtc={data?.last_seen_utc}
                variant="flat"
                fillMode="line"
              />
            </div>

            {/* Energia acumulada full-width */}
            <HistoryChart
              title="Energia acumulada"
              unit="kWh"
              series={accumSeries}
              windowKey={wk}
              chartHeightClass={CHART_HEIGHT}
              delayMs={300}
              muted={muted}
              lastSeenUtc={data?.last_seen_utc}
              variant="flat"
              fillMode="line"
            />

            {bars.length === 0 && !hasPower && !hasVoltage && !hasCurrent && !hasPf && !hasAccum && (
              <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center">
                <Battery className="size-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Sem medições no período · Aguardando dados do medidor SM-3EGW.
                </p>
              </div>
            )}
          </section>

          {/* Rodapé */}
          {data?.last_seen_utc && (
            <footer className="flex flex-col items-start justify-between gap-2 border-t border-border pt-5 text-xs text-muted-foreground sm:flex-row sm:items-center">
              <span className="flex items-center gap-1.5">
                {data.online ? (
                  <Signal className="size-3.5 text-emerald-500" />
                ) : (
                  <WifiOff className="size-3.5 text-destructive" />
                )}
                Última leitura:{' '}
                <span className="tabular-nums text-foreground/70">{fmtLastSeen(data.last_seen_utc)}</span>
              </span>
              <span>Atualiza automaticamente a cada {AUTO_REFRESH_MS / 1000}s</span>
            </footer>
          )}
        </main>
      )}
    </div>
  );
}
