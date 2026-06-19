import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Droplets, Gauge, Activity, AlertTriangle,
  TrendingUp, TrendingDown, LineChart, Bell, MapPin,
} from 'lucide-react';

import {
  installations, tankGroups, buildDashboardSnapshot, buildInstallationMetrics,
} from '../mocks/hospitalSantaAnaMock';
import LiquidHero from '../components/installation/LiquidHero';
import StatusRing from '../components/installation/StatusRing';
import KpiCard from '../components/dashboard/KpiCard';
import NavCard from '../components/installation/NavCard';
import { HospitalHydraulicScheme } from '../components/topology/HospitalHydraulicScheme';
import { InstallationAlertsCard } from '../components/dashboard/InstallationAlertsCard';
import { useCountUp } from '../hooks/useCountUp';
import { cn } from '../lib/cn';
import type { InstallationStatus } from '../types/telemetry';

const statusLabel: Record<InstallationStatus, string> = {
  online:  'Online',
  alert:   'Alerta',
  offline: 'Offline',
};

const Installation = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const installation = useMemo(
    () => installations.find((i) => i.id === id) ?? installations[0],
    [id],
  );

  const snapshot = useMemo(() => buildDashboardSnapshot('24h'), []);
  const metrics = useMemo(() => buildInstallationMetrics(), []);
  const consumoAnimated = useCountUp(metrics.consumoHoje, 1300);
  const variacaoPositiva = metrics.variacaoPct >= 0;

  return (
    <div className="min-h-screen w-full bg-secondary">
      {/* ── Header ──────────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate('/menu')}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar ao mapa
          </button>

          <div className="flex items-center gap-3 text-primary">
            <img
              src="/santana-coat.png"
              alt="Brasão"
              className="h-10 w-10 object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight hidden sm:block">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Santana de Parnaíba</p>
              <p className="text-[12px] font-semibold text-foreground">Telemetria Hídrica</p>
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

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-8 sm:py-10 space-y-8">
        {/* ── Hero ──────────────────────────────────────── */}
        <LiquidHero>
          <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <div className="flex items-center gap-2 text-primary-foreground/85">
                <MapPin className="h-3.5 w-3.5" />
                <span className="text-[10px] uppercase tracking-[0.25em]">
                  Instalação · Santana de Parnaíba / SP
                </span>
              </div>

              <h1 className="mt-4 text-4xl sm:text-5xl lg:text-6xl tracking-tight text-white animate-reveal-mask font-display"
                  style={{ animationDelay: '120ms' }}>
                {installation.name}
              </h1>

              <p className="mt-3 text-sm sm:text-base text-primary-foreground/90 animate-drop-in"
                 style={{ animationDelay: '260ms' }}>
                {installation.address}
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-3 animate-drop-in"
                   style={{ animationDelay: '380ms' }}>
                <span
                  className={cn(
                    'inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider backdrop-blur-sm',
                    installation.status === 'online'  && 'bg-primary-glow/30 text-white',
                    installation.status === 'alert'   && 'bg-accent/40 text-white',
                    installation.status === 'offline' && 'bg-destructive/40 text-white',
                  )}
                >
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      installation.status === 'online'  && 'bg-primary-glow',
                      installation.status === 'alert'   && 'bg-accent',
                      installation.status === 'offline' && 'bg-destructive',
                    )}
                  />
                  {statusLabel[installation.status]}
                </span>
                <span className="text-[11px] text-primary-foreground/85">
                  Atualizado há {metrics.ultimaLeituraMin} min
                </span>
              </div>
            </div>

            <div
              className="relative w-full max-w-sm rounded-2xl border border-white/20 bg-[hsl(220_50%_18%)]/70 p-6 backdrop-blur-md shadow-card animate-drop-in"
              style={{ animationDelay: '500ms' }}
            >
              <div className="flex items-center gap-5">
                <StatusRing status={installation.status}>
                  <Droplets className="h-9 w-9" />
                </StatusRing>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.22em] text-primary-foreground/85">
                    Consumo hoje
                  </p>
                  <p className="mt-1 text-4xl font-bold tabular-nums text-white">
                    {consumoAnimated.toFixed(2)}
                    <span className="ml-1 text-base font-medium text-primary-foreground/85">m³</span>
                  </p>
                  <p className={cn(
                    'mt-1 inline-flex items-center gap-1 text-xs font-medium',
                    variacaoPositiva ? 'text-accent' : 'text-primary-glow',
                  )}>
                    {variacaoPositiva ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
                    {Math.abs(metrics.variacaoPct).toFixed(1)}% vs. período anterior
                  </p>
                </div>
              </div>
            </div>
          </div>
        </LiquidHero>

        {/* ── Esquema hidráulico ───────────────────────── */}
        <HospitalHydraulicScheme
          tankGroups={tankGroups}
          vazao={metrics.vazao}
          vazao1={snapshot.vazao1}
          vazao2={snapshot.vazao2}
          pressao1={snapshot.pressao1}
          pressao2={snapshot.pressao2}
        />

        {/* ── Métricas em tempo real ───────────────────── */}
        <section>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-3">
            Métricas em tempo real
          </p>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard icon={Gauge}         label="Vazão"      value={metrics.vazao}   suffix="L/min" decimals={1} spark={metrics.spark}                  delayMs={0}   />
            <KpiCard icon={Activity}      label="Pressão"    value={metrics.pressao} suffix="MCA"   decimals={2} spark={metrics.spark.slice().reverse()} delayMs={80}  />
            <KpiCard icon={Droplets}      label="Total (24h)" value={metrics.totalMes} suffix="m³"                spark={metrics.spark}                  delayMs={160} />
            <KpiCard icon={AlertTriangle} label="Anomalias"  value={metrics.anomalias}                                                                  delayMs={240} tone={metrics.anomalias > 0 ? 'accent' : 'default'} />
          </div>
        </section>

        {/* ── Card de alertas ──────────────────────────── */}
        <InstallationAlertsCard installationId={id} />

        {/* ── Explorar ─────────────────────────────────── */}
        <section>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-3">Explorar</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <NavCard
              icon={LineChart}
              title="Dashboard"
              description="Curvas de consumo, vazão, pressão e nível em tempo real."
              delayMs={0}
              onClick={() => navigate(`/instalacao/${installation.id}/dashboard`)}
            />
            <NavCard
              icon={Bell}
              title="Alertas"
              description="Vazamentos, picos e eventos do dispositivo."
              delayMs={160}
              onClick={() => navigate('/alertas')}
            />
          </div>
        </section>

        <footer className="pt-4 pb-8 text-center text-[11px] text-muted-foreground">
          Coordenadas {installation.lat.toFixed(4)}, {installation.lng.toFixed(4)}
        </footer>
      </main>
    </div>
  );
};

export default Installation;
