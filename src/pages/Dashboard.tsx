import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Droplets, Gauge, Battery, SignalHigh, Clock, Radio, Activity } from 'lucide-react';

import FiltersBar from '../components/dashboard/FiltersBar';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { WINDOW_TO_HOURS, DEVICE_COLORS } from '../constants/dashboard';
import type {
  WindowKey,
  FilterMode,
  DashDevice,
  InstallationDashboardResponse,
} from '../types/telemetry';

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toFixed(digits);
}

function fmtDateTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' });
}

function deviceLabel(d: DashDevice): string {
  return d.label ?? `Remota ${d.imei.slice(-4)}`;
}

// Constrói uma ChartSeries por remota para uma métrica (só com dados).
function buildSeries(devices: DashDevice[], metric: string): ChartSeries[] {
  return devices
    .map((d, i) => ({
      key: `dev_${d.device_id}`,
      label: deviceLabel(d),
      color: DEVICE_COLORS[i % DEVICE_COLORS.length],
      data: d.series?.[metric] ?? [],
    }))
    .filter((s) => s.data.length > 0);
}

// ── Componente ──────────────────────────────────────────────────────────────

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

  const levelPctSeries = useMemo(() => buildSeries(devices, 'level_pct'), [devices]);
  const levelMSeries = useMemo(() => buildSeries(devices, 'level_m'), [devices]);
  const currentMaSeries = useMemo(() => buildSeries(devices, 'current_ma'), [devices]);

  const hasAnySeries =
    levelPctSeries.length > 0 || levelMSeries.length > 0 || currentMaSeries.length > 0;

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
                Santana de Parnaíba
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

        {/* Resumo da instalação */}
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-soft">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1.5 text-xs font-medium text-foreground">
            <Radio className="h-3.5 w-3.5 text-primary" />
            Remotas ativas:{' '}
            <span className="tabular-nums">
              {data ? `${data.active_count}/${data.device_count}` : '—'}
            </span>
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1.5 text-xs font-medium text-foreground">
            <Clock className="h-3.5 w-3.5 text-primary" />
            Última comunicação:{' '}
            <span className="tabular-nums">{fmtDateTime(data?.last_seen_utc ?? null)}</span>
          </span>
          {loading && (
            <span className="text-[11px] text-muted-foreground animate-pulse">Carregando…</span>
          )}
        </div>

        {/* Erro */}
        {error && (
          <div className="rounded-2xl border border-destructive/40 bg-destructive/10 p-5 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Estado vazio */}
        {!loading && !error && devices.length === 0 && (
          <EmptyState
            title="Nenhuma remota registrada"
            message="Ainda não há remotas vinculadas a esta instalação. Os dispositivos aparecem automaticamente assim que enviam o primeiro pacote."
          />
        )}

        {!loading && !error && devices.length > 0 && !hasAnySeries && (
          <EmptyState
            title="Sem leituras na janela selecionada"
            message="As remotas estão registradas, mas não há leituras no período escolhido. Tente uma janela maior ou aguarde o próximo envio."
          />
        )}

        {/* Cards por remota */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {devices.map((d) => (
              <DeviceCard key={d.device_id} device={d} />
            ))}
          </div>
        )}

        {/* Gráficos — uma linha por remota */}
        {hasAnySeries && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {levelPctSeries.length > 0 && (
              <HistoryChart
                title="Nível (%)"
                unit="%"
                windowKey={windowKey}
                yDomain={[0, 100]}
                series={levelPctSeries}
                delayMs={80}
              />
            )}
            {levelMSeries.length > 0 && (
              <HistoryChart
                title="Nível (m)"
                unit="m"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={48}
                series={levelMSeries}
                delayMs={160}
              />
            )}
            {currentMaSeries.length > 0 && (
              <HistoryChart
                title="Corrente do transdutor (mA)"
                unit="mA"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={48}
                lineType="linear"
                tooltipNote="canal analógico 4–20 mA (técnico)"
                series={currentMaSeries}
                delayMs={240}
              />
            )}
          </div>
        )}

        <p className="text-[11px] text-muted-foreground">
          Janela {windowKey} · {devices.length} remota(s) ·{' '}
          {data?.last_seen_utc ? `atualizado ${fmtDateTime(data.last_seen_utc)}` : 'sem dados'}
        </p>
      </main>
    </div>
  );
};

// ── Card por remota ─────────────────────────────────────────────────────────

function DeviceCard({ device }: { device: DashDevice }) {
  const l = device.latest;
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Remota</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{deviceLabel(device)}</h3>
          <p className="text-[11px] text-muted-foreground tabular-nums">IMEI {device.imei}</p>
        </div>
        <span
          className={
            'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ' +
            (device.active
              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30'
              : 'bg-muted text-muted-foreground border-border')
          }
        >
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {device.active ? 'Ativa' : 'Sem sinal'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Metric icon={<Gauge className="h-3.5 w-3.5" />} label="Nível" value={`${fmt(l.level_pct, 1)} %`} />
        <Metric icon={<Droplets className="h-3.5 w-3.5" />} label="Nível (m)" value={`${fmt(l.level_m, 2)} m`} />
        <Metric icon={<Battery className="h-3.5 w-3.5" />} label="Bateria" value={`${fmt(l.battery_v, 2)} V`} />
        <Metric icon={<SignalHigh className="h-3.5 w-3.5" />} label="Sinal" value={l.signal == null ? '—' : `${fmt(l.signal, 0)} dBm`} />
        <Metric icon={<Activity className="h-3.5 w-3.5" />} label="Corrente" value={`${fmt(l.current_ma, 2)} mA`} />
        <Metric icon={<Clock className="h-3.5 w-3.5" />} label="Última com." value={fmtDateTime(device.last_seen_utc)} />
      </div>
    </div>
  );
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-3">
      <p className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground leading-tight">
        <span className="text-primary">{icon}</span>
        {label}
      </p>
      <p className="mt-1.5 text-sm font-bold text-foreground tabular-nums">{value}</p>
    </div>
  );
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

export default Dashboard;
