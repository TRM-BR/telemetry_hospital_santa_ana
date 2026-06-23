import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Droplets } from 'lucide-react';
import { api } from '../services/api';
import { isSignalLost, fillSilenceWithZeros } from '../lib/series';

import FiltersBar from '../components/dashboard/FiltersBar';
import { FlowBarChart } from '../components/dashboard/FlowBarChart';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { LevelGaugeCard } from '../components/dashboard/LevelGaugeCard';
import { WINDOW_TO_HOURS, CHART_COLORS, DEFAULT_SHIFT, SHIFT_LS_KEY } from '../constants/dashboard';
import type {
  WindowKey,
  FilterMode,
  DashDevice,
  InstallationDashboardResponse,
} from '../types/telemetry';

function groupLabel(i: number) { return `Grupo ${i + 1}`; }

function buildSeries(devices: DashDevice[], metric: string, winStart: number, nowMs: number): ChartSeries[] {
  return devices
    .filter((d) => (d.series?.[metric]?.length ?? 0) > 0)
    .map((d, i) => ({
      key: `dev_${d.device_id}`,
      label: groupLabel(i),
      color: CHART_COLORS[i % CHART_COLORS.length],
      data: fillSilenceWithZeros(d.series?.[metric] ?? [], winStart, nowMs),
    }));
}

function buildSeriesForDevice(device: DashDevice, metric: string, idx: number, winStart: number, nowMs: number): ChartSeries[] {
  const data = fillSilenceWithZeros(device.series?.[metric] ?? [], winStart, nowMs);
  return [{
    key: `dev_${device.device_id}`,
    label: groupLabel(idx),
    color: 'var(--primary)',
    data,
  }];
}

function deviceSignalLost(device: DashDevice): boolean {
  return isSignalLost(device.last_seen_utc);
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

const CHART_HEIGHT = 'h-[280px]';
const AUTO_REFRESH_MS = 30_000;

const Dashboard = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [mode, setMode] = useState<FilterMode>('janela');
  const [windowKey, setWindowKey] = useState<WindowKey>('24h');
  const [shift, setShift] = useState<{ start: string; end: string }>(() => {
    try {
      const saved = localStorage.getItem(SHIFT_LS_KEY);
      if (saved) return JSON.parse(saved);
    } catch { /* ignore */ }
    return DEFAULT_SHIFT;
  });

  const [data, setData] = useState<InstallationDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const hours = WINDOW_TO_HOURS[windowKey];

  const load = useCallback(
    async (signal: AbortSignal, silent = false) => {
      if (!silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const json = await api<InstallationDashboardResponse>(
          `/installations/${id}/dashboard?hours=${hours}&shift_start=${shift.start}&shift_end=${shift.end}`,
          { signal },
        );
        setData(json);
        setError(null);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        if (!silent) {
          setError('Não foi possível carregar os dados do dashboard.');
          setData(null);
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [id, hours, shift.start, shift.end],
  );

  useEffect(() => {
    let ctrl = new AbortController();
    load(ctrl.signal);

    const iv = setInterval(() => {
      ctrl.abort();
      ctrl = new AbortController();
      load(ctrl.signal, true);
    }, AUTO_REFRESH_MS);

    return () => {
      ctrl.abort();
      clearInterval(iv);
    };
  }, [load]);

  const devices = useMemo(() => data?.devices ?? [], [data]);

  // Linha 2: série por remota (individual)
  const perDeviceLevelPct = useMemo(() => {
    const now = Date.now();
    const winStart = now - hours * 3_600_000;
    return devices.map((d, i) => buildSeriesForDevice(d, 'level_pct', i, winStart, now));
  }, [devices, hours]);

  // Linha 3: comparativo multi-linha
  const levelPctSeries = useMemo(() => {
    const now = Date.now();
    const winStart = now - hours * 3_600_000;
    return buildSeries(devices, 'level_pct', winStart, now);
  }, [devices, hours]);

  const levelMSeries = useMemo(() => {
    const now = Date.now();
    const winStart = now - hours * 3_600_000;
    return buildSeries(devices, 'level_m', winStart, now);
  }, [devices, hours]);

  // Linha 4: vazão por grupo
  const perDeviceFlowHourly = useMemo(() => {
    const now = Date.now();
    const winStart = now - hours * 3_600_000;
    return devices.map((d, i) => buildSeriesForDevice(d, 'flow_hourly_lph', i, winStart, now));
  }, [devices, hours]);

  const perDeviceFlowNet = useMemo(() => {
    const now = Date.now();
    const winStart = now - hours * 3_600_000;
    return devices.map((d, i) => buildSeriesForDevice(d, 'flow_consumo_lph', i, winStart, now));
  }, [devices, hours]);

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
          consumptionSummary={data?.consumption_summary}
          shiftStart={shift.start}
          shiftEnd={shift.end}
          onShiftChange={(start, end) => {
            const next = { start, end };
            setShift(next);
            try { localStorage.setItem(SHIFT_LS_KEY, JSON.stringify(next)); } catch { /* ignore */ }
          }}
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

        {/* Linha 1 — Gauge de nível por remota */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-stretch">
            {devices.map((d, i) => (
              <LevelGaugeCard
                key={d.device_id}
                device={d}
                groupIndex={i}
                signalLost={deviceSignalLost(d)}
              />
            ))}
          </div>
        )}

        {/* Linha 2 — Comparativo multi-linha (sem dim: cada linha cai a zero no silêncio) */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
            {levelPctSeries.length > 0 && (
              <HistoryChart
                title="Histórico de Nível Geral (%)"
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
                title="Histórico de Nível Geral (m)"
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

        {/* Linha 3 — Histórico individual por remota */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
            {devices.map((d, i) => {
              const series = perDeviceLevelPct[i];
              if (!series || series.length === 0) return null;
              const signalLost = deviceSignalLost(d);
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
                  muted={signalLost}
                  lastSeenUtc={d.last_seen_utc}
                />
              );
            })}
          </div>
        )}

        {/* Linha 4 — Vazão por grupo */}
        {devices.length > 0 && (
          <>
            {/* Barras: vazão horária assinada */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
              {devices.map((d, i) => {
                const series = perDeviceFlowHourly[i];
                if (!series || series.length === 0) return null;
                const signalLost = deviceSignalLost(d);
                return (
                  <FlowBarChart
                    key={d.device_id}
                    title={`Vazão (L/h) — ${groupLabel(i)}`}
                    data={series[0].data}
                    label={groupLabel(i)}
                    windowKey={windowKey}
                    chartHeightClass={CHART_HEIGHT}
                    delayMs={i * 80}
                    muted={signalLost}
                    lastSeenUtc={d.last_seen_utc}
                  />
                );
              })}
            </div>

            {/* Linhas: evolução contínua da vazão */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 items-stretch">
              {devices.map((d, i) => {
                const series = perDeviceFlowNet[i];
                if (!series || series.length === 0) return null;
                const signalLost = deviceSignalLost(d);
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
                    muted={signalLost}
                    lastSeenUtc={d.last_seen_utc}
                  />
                );
              })}
            </div>
          </>
        )}

        <div className="space-y-1">
          <p className="text-[11px] text-muted-foreground">
            Janela {windowKey} · {devices.length} remota(s) ·{' '}
            {data?.last_seen_utc ? `atualizado ${fmtDateTime(data.last_seen_utc)}` : 'sem dados'}
          </p>
          {data && data.capacidade_total_l > 0 && (
            <p className="text-[11px] text-muted-foreground/70">
              Total: {Math.round(data.volume_total_l).toLocaleString('pt-BR')} L /{' '}
              {Math.round(data.capacidade_total_l).toLocaleString('pt-BR')} L · faltam{' '}
              {Math.round(data.faltante_total_l).toLocaleString('pt-BR')} L
            </p>
          )}
        </div>
      </main>
    </div>
  );
};

export default Dashboard;
