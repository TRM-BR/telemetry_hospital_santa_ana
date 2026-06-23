import { useCallback, useEffect, useMemo, useState } from 'react';
import { Radio } from 'lucide-react';
import { api } from '../services/api';

import FiltersBar from '../components/dashboard/FiltersBar';
import HistoryChart, { type ChartSeries } from '../components/dashboard/HistoryChart';
import { DeviceCard, deviceLabel, fmtDateTime } from '../components/dashboard/DeviceCard';
import { WINDOW_TO_HOURS, DEVICE_COLORS } from '../constants/dashboard';
import type {
  WindowKey,
  FilterMode,
  DashDevice,
  InstallationDashboardResponse,
} from '../types/telemetry';

const INSTALLATION_SLUG = 'hospital-santa-ana';

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

function ArrivalList({ devices }: { devices: DashDevice[] }) {
  const entries = useMemo(() => {
    return devices.flatMap((d, i) => {
      const pts = d.series?.['current_ma'] ?? [];
      return pts.map((p) => ({
        label: deviceLabel(d),
        color: DEVICE_COLORS[i % DEVICE_COLORS.length],
        ts: p.t,
      }));
    }).sort((a, b) => b.ts - a.ts).slice(0, 50);
  }, [devices]);

  if (entries.length === 0) return null;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-1">Histórico de chegada</p>
      <h3 className="text-lg font-semibold text-foreground mb-4">Pacotes recentes</h3>
      <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
        {entries.map((e, idx) => (
          <div
            key={idx}
            className="flex items-center gap-3 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs"
          >
            <span
              className="h-2 w-2 flex-shrink-0 rounded-full"
              style={{ background: `hsl(${e.color})` }}
            />
            <span className="font-medium text-foreground flex-1">{e.label}</span>
            <span className="text-muted-foreground tabular-nums">
              {fmtDateTime(new Date(e.ts).toISOString())}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center shadow-soft">
      <Radio className="mx-auto h-8 w-8 text-muted-foreground/60" />
      <h3 className="mt-3 text-base font-semibold text-foreground">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

const Remotas = () => {
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
        const json = await api<InstallationDashboardResponse>(
          `/installations/${INSTALLATION_SLUG}/dashboard?hours=${hours}`,
          { signal },
        );
        setData(json);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setError('Não foi possível carregar os dados das remotas.');
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [hours],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load, refreshKey]);

  const devices = useMemo(() => data?.devices ?? [], [data]);

  const batterySeries  = useMemo(() => buildSeries(devices, 'battery_v'), [devices]);
  const signalSeries   = useMemo(() => buildSeries(devices, 'signal'), [devices]);
  const currentSeries  = useMemo(() => buildSeries(devices, 'current_ma'), [devices]);

  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <div className="flex items-center gap-3 text-primary">
            <Radio className="h-5 w-5" />
            <div className="leading-tight">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Santana do Parnaíba
              </p>
              <p className="text-[12px] font-semibold text-foreground">Monitoramento de Remotas</p>
            </div>
          </div>
          {loading && (
            <span className="text-[11px] text-muted-foreground animate-pulse">Carregando…</span>
          )}
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

        {/* Cards por remota */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {devices.map((d) => (
              <DeviceCard key={d.device_id} device={d} />
            ))}
          </div>
        )}

        {/* Gráficos: bateria, sinal, corrente */}
        {devices.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {batterySeries.length > 0 && (
              <HistoryChart
                title="Bateria (V)"
                unit="V"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={48}
                series={batterySeries}
                chartHeightClass="h-[220px]"
                delayMs={80}
              />
            )}
            {signalSeries.length > 0 && (
              <HistoryChart
                title="Sinal (dBm)"
                unit="dBm"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={52}
                series={signalSeries}
                chartHeightClass="h-[220px]"
                delayMs={160}
              />
            )}
            {currentSeries.length > 0 && (
              <HistoryChart
                title="Corrente do transdutor (mA)"
                unit="mA"
                windowKey={windowKey}
                yDomain={[0, 'auto']}
                yAxisWidth={48}
                lineType="linear"
                tooltipNote="canal analógico 4–20 mA (técnico)"
                series={currentSeries}
                chartHeightClass="h-[220px]"
                delayMs={240}
              />
            )}
          </div>
        )}

        {/* Histórico de chegada */}
        {devices.length > 0 && <ArrivalList devices={devices} />}

        <p className="text-[11px] text-muted-foreground">
          Janela {windowKey} · {devices.length} remota(s) ·{' '}
          {data?.last_seen_utc
            ? `atualizado ${new Date(data.last_seen_utc).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })}`
            : 'sem dados'}
        </p>
      </main>
    </div>
  );
};

export default Remotas;
