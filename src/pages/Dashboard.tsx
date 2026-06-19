import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Droplets } from 'lucide-react';

import FiltersBar from '../components/dashboard/FiltersBar';
import { FlowBarChart } from '../components/dashboard/FlowBarChart';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { LevelGaugeCard } from '../components/dashboard/LevelGaugeCard';
import { WINDOW_TO_HOURS, CHART_COLORS } from '../constants/dashboard';
import type {
  WindowKey,
  FilterMode,
  DashDevice,
  FillReferenceSource,
  InstallationDashboardResponse,
} from '../types/telemetry';

function groupLabel(i: number) { return `Grupo ${i + 1}`; }

function buildSeries(devices: DashDevice[], metric: string): ChartSeries[] {
  return devices
    .map((d, i) => ({
      key: `dev_${d.device_id}`,
      label: groupLabel(i),
      color: CHART_COLORS[i % CHART_COLORS.length],
      data: d.series?.[metric] ?? [],
    }))
    .filter((s) => s.data.length > 0);
}

function buildSeriesForDevice(device: DashDevice, metric: string, idx: number): ChartSeries[] {
  const data = device.series?.[metric] ?? [];
  if (data.length === 0) return [];
  return [{
    key: `dev_${device.device_id}`,
    label: groupLabel(idx),
    color: 'var(--primary)',
    data,
  }];
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center shadow-soft">
      <Droplets className="mx-auto h-8 w-8 text-muted-foreground/60" />
      <h3 className="mt-3 text-base font-semibold text-foreground">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}

const FILL_REF_NOTE: Record<FillReferenceSource, string> = {
  estimated_daily_max_p90:
    'Nível em %: 100% = cheio operacional estimado pelo pico típico diário dos últimos 30 dias.',
  provisional_p90:
    'Nível em %: 100% = referência provisória pelo pico típico diário do histórico disponível.',
  provisional_observed_max:
    'Nível em %: 100% = referência provisória pelo maior nível observado até agora.',
  none: 'Nível em %: exibindo percentual bruto da escala do sensor (sem histórico suficiente para estimar o cheio operacional).',
};

function fillRefNote(devices: DashDevice[]): string | null {
  if (devices.length === 0) return null;
  // Usa a source do primeiro device com source != 'none'; se todos 'none', usa 'none'.
  const priority: FillReferenceSource[] = [
    'estimated_daily_max_p90',
    'provisional_p90',
    'provisional_observed_max',
    'none',
  ];
  for (const src of priority) {
    if (devices.some((d) => d.fill_reference_source === src)) {
      return FILL_REF_NOTE[src];
    }
  }
  return null;
}

const CHART_HEIGHT = 'h-[280px]';

const Dashboard = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [mode, setMode] = useState<FilterMode>('janela');
  const [windowKey, setWindowKey] = useState<WindowKey>('24h');
  const [refreshKey, setRefreshKey] = useState(0);

  const [data, setData] = useState<InstallationDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const hours = WINDOW_TO_HOURS[windowKey];

  const load = useCallback(
    async (signal: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/v1/installations/${id}/dashboard?hours=${hours}`,
          { signal },
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: InstallationDashboardResponse = await res.json();
        setData(json);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setError('Não foi possível carregar os dados do dashboard.');
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [id, hours],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load, refreshKey]);

  const devices = useMemo(() => data?.devices ?? [], [data]);

  // Linha 2: série por remota (individual)
  const perDeviceLevelPct = useMemo(
    () => devices.map((d, i) => buildSeriesForDevice(d, 'level_pct', i)),
    [devices],
  );

  // Linha 3: comparativo multi-linha
  const levelPctSeries = useMemo(() => buildSeries(devices, 'level_pct'), [devices]);
  const levelMSeries   = useMemo(() => buildSeries(devices, 'level_m'), [devices]);

  const hasSeries = levelPctSeries.length > 0 || levelMSeries.length > 0;

  // Linha 4: vazão por grupo (flow_hourly_lph = barras; flow_net_lph = linhas)
  const perDeviceFlowHourly = useMemo(
    () => devices.map((d, i) => buildSeriesForDevice(d, 'flow_hourly_lph', i)),
    [devices],
  );
  const perDeviceFlowNet = useMemo(
    () => devices.map((d, i) => buildSeriesForDevice(d, 'flow_consumo_lph', i)),
    [devices],
  );
  const hasFlowSeries = perDeviceFlowHourly.some((s) => s.length > 0);

  const installationName = data?.installation_name ?? 'Hospital Santa Ana';

  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate(`/instalacao/${id}`)}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar à instalação
          </button>

          <div className="flex items-center gap-3 text-primary">
            <img
              src="/santana-coat.png"
              alt="Brasão"
              className="h-10 w-10 object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight hidden sm:block">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Santana do Parnaíba
              </p>
              <p className="text-[12px] font-semibold text-foreground">
                Dashboard · {installationName}
              </p>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Powered by</span>
            <span className="inline-flex items-center gap-1 font-display text-sm text-primary">
              <Droplets className="h-3.5 w-3.5" />
              Vector
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-8 space-y-5">
        <FiltersBar
          mode={mode}
          onModeChange={setMode}
          windowKey={windowKey}
          onWindowChange={setWindowKey}
          onRefresh={() => setRefreshKey((k) => k + 1)}
        />

        {loading && (
          <p className="text-[11px] text-muted-foreground animate-pulse px-1">Carregando…</p>
        )}

        {error && (
          <div className="rounded-2xl border border-destructive/40 bg-destructive/10 p-5 text-sm text-destructive">
            {error}
          </div>
        )}

        {!loading && !error && devices.length === 0 && (
          <EmptyState
            title="Nenhuma remota registrada"
            message="Ainda não há remotas vinculadas a esta instalação. Os dispositivos aparecem automaticamente assim que enviam o primeiro pacote."
          />
        )}

        {!loading && !error && devices.length > 0 && !hasSeries && (
          <EmptyState
            title="Sem leituras na janela selecionada"
            message="As remotas estão registradas, mas não há leituras no período escolhido. Tente uma janela maior ou aguarde o próximo envio."
          />
        )}

        {/* Linha 1 — Gauge de nível por remota */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-stretch">
            {devices.map((d, i) => (
              <LevelGaugeCard key={d.device_id} device={d} groupIndex={i} />
            ))}
          </div>
        )}

        {/* Linha 2 — Histórico individual por remota */}
        {devices.length > 0 && perDeviceLevelPct.some((s) => s.length > 0) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
            {devices.map((d, i) => {
              const series = perDeviceLevelPct[i];
              if (!series || series.length === 0) return null;
              return (
                <HistoryChart
                  key={d.device_id}
                  title={`Histórico de Nível (%) — ${groupLabel(i)}`}
                  unit="%"
                  windowKey={windowKey}
                  yDomain={[0, 100]}
                  yAxisWidth={52}
                  series={series}
                  chartHeightClass={CHART_HEIGHT}
                  delayMs={i * 80}
                />
              );
            })}
          </div>
        )}

        {/* Linha 3 — Comparativo multi-linha */}
        {hasSeries && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
            {levelPctSeries.length > 0 && (
              <HistoryChart
                title="Histórico de Nível (%)"
                unit="%"
                windowKey={windowKey}
                yDomain={[0, 100]}
                yAxisWidth={52}
                series={levelPctSeries}
                chartHeightClass={CHART_HEIGHT}
                delayMs={0}
              />
            )}
            {levelMSeries.length > 0 && (
              <HistoryChart
                title="Histórico de Nível (m)"
                unit="m"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={52}
                series={levelMSeries}
                chartHeightClass={CHART_HEIGHT}
                delayMs={80}
              />
            )}
          </div>
        )}

        {/* Linha 4 — Vazão por grupo */}
        {hasFlowSeries && (
          <>
            {/* Barras: vazão horária assinada */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
              {devices.map((d, i) => {
                const hourlyData = d.series?.['flow_hourly_lph'] ?? [];
                if (hourlyData.length === 0) return null;
                return (
                  <FlowBarChart
                    key={d.device_id}
                    title={`Vazão (L/h) — ${groupLabel(i)}`}
                    data={hourlyData}
                    label={groupLabel(i)}
                    windowKey={windowKey}
                    chartHeightClass={CHART_HEIGHT}
                    delayMs={i * 80}
                  />
                );
              })}
            </div>

            {/* Linhas: evolução contínua da vazão */}
            {perDeviceFlowNet.some((s) => s.length > 0) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
                {devices.map((d, i) => {
                  const series = perDeviceFlowNet[i];
                  if (!series || series.length === 0) return null;
                  return (
                    <HistoryChart
                      key={d.device_id}
                      title={`Consumo (L/h) — ${groupLabel(i)}`}
                      unit="L/h"
                      windowKey={windowKey}
                      yDomain={[0, 'auto']}
                      yAxisWidth={52}
                      series={series}
                      chartHeightClass={CHART_HEIGHT}
                      delayMs={i * 80}
                    />
                  );
                })}
              </div>
            )}
          </>
        )}

        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">
            Janela {windowKey} · {devices.length} remota(s) ·{' '}
            {data?.last_seen_utc ? `atualizado ${fmtDateTime(data.last_seen_utc)}` : 'sem dados'}
          </p>
          {fillRefNote(devices) && (
            <p className="text-[11px] text-muted-foreground/70">
              {fillRefNote(devices)}
            </p>
          )}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
