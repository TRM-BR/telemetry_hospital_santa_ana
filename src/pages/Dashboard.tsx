import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Droplets } from 'lucide-react';

import { installations, buildDashboardSnapshot } from '../mocks/hospitalSantaAnaMock';
import FiltersBar from '../components/dashboard/FiltersBar';
import LevelCard from '../components/dashboard/LevelCard';
import HistoryChart from '../components/dashboard/HistoryChart';
import type { WindowKey, FilterMode } from '../types/telemetry';

const Dashboard = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const installation = useMemo(
    () => installations.find((i) => i.id === id) ?? installations[0],
    [id],
  );

  const [mode, setMode] = useState<FilterMode>('janela');
  const [windowKey, setWindowKey] = useState<WindowKey>('24h');
  const [refreshKey, setRefreshKey] = useState(0);

  // Snapshot regenerado quando windowKey ou refreshKey muda
  const snapshot = useMemo(
    () => buildDashboardSnapshot(windowKey),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [windowKey, refreshKey],
  );

  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate(`/instalacao/${installation.id}`)}
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
                Dashboard · {installation.name}
              </p>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Powered by</span>
            <span className="inline-flex items-center gap-1 font-display text-sm text-primary">
              <Droplets className="h-3.5 w-3.5" />
              Verth
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

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <LevelCard snapshot={snapshot} />

          <HistoryChart
            title="Histórico de Nível"
            unit="%"
            windowKey={windowKey}
            yDomain={[0, 100]}
            tooltipNote="nível estimado por pressão"
            badges={[{ label: 'Nível', value: `${snapshot.nivelAtual.toFixed(1)} %` }]}
            series={[{
              key: 'nivel',
              label: 'Nível',
              color: 'var(--primary)',
              data: snapshot.series.nivel,
            }]}
            delayMs={80}
          />

          <HistoryChart
            title="Histórico de Vazão"
            unit="L/h"
            windowKey={windowKey}
            yDomain={[0, 'auto']}
            lineType="linear"
            chartHeightClass="h-[320px]"
            yAxisWidth={52}
            badges={[
              { label: 'V1', value: `${snapshot.vazao1.toFixed(2)} L/h` },
              { label: 'V2', value: `${snapshot.vazao2.toFixed(2)} L/h` },
            ]}
            series={[
              { key: 'v1', label: 'Vazão 1', color: 'var(--primary)', data: snapshot.series.vazao1 },
              { key: 'v2', label: 'Vazão 2', color: 'var(--accent)',  data: snapshot.series.vazao2 },
            ]}
            delayMs={160}
          />

          <HistoryChart
            title="Histórico de Pressão"
            unit="MCA"
            windowKey={windowKey}
            yDomain="smart"
            chartHeightClass="h-[320px]"
            yAxisWidth={52}
            badges={[
              { label: 'P1', value: `${snapshot.pressao1.toFixed(2)} MCA` },
              { label: 'P2', value: `${snapshot.pressao2.toFixed(2)} MCA` },
            ]}
            series={[
              { key: 'p1', label: 'Pressão 1', color: 'var(--primary)', data: snapshot.series.pressao1 },
              { key: 'p2', label: 'Pressão 2', color: 'var(--accent)',  data: snapshot.series.pressao2 },
            ]}
            delayMs={240}
          />
        </div>

        <p className="text-[11px] text-muted-foreground">
          Janela {windowKey} · Atualizado com sucesso ·{' '}
          <span className="tabular-nums">
            {snapshot.ultimaLeitura.toLocaleTimeString('pt-BR')}
          </span>
        </p>
      </main>
    </div>
  );
};

export default Dashboard;
