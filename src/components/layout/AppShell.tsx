import { Building2, Wifi, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import type { Installation } from '../../types/telemetry';
import { MockDataBadge } from '../dashboard/MockDataBadge';
import { StatusBadge } from '../dashboard/StatusBadge';
import { formatM3 } from '../../lib/format';

interface AppShellProps {
  installation: Installation;
  children: ReactNode;
}

export function AppShell({ installation, children }: AppShellProps) {
  return (
    <div className="min-h-svh bg-gradient-page">
      {/* ── Header sticky ─────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-3 sm:px-8">

          {/* Logo / produto */}
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-header shadow-button">
              <Wifi className="h-4.5 w-4.5 text-white" style={{ width: 18, height: 18 }} />
            </div>
            <div className="leading-tight hidden sm:block">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Telemetry
              </p>
              <p className="text-[12px] font-semibold text-foreground">
                Hospital Santa Ana
              </p>
            </div>
          </div>

          {/* Badge POC (central em desktop) */}
          <div className="flex items-center gap-3">
            <MockDataBadge />
            <StatusBadge status={installation.status} />
          </div>

          {/* Última leitura + consumo referência */}
          <div className="hidden md:flex flex-col items-end text-right">
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <WifiOff className="h-3 w-3 text-amber-500" />
              <span className="text-amber-600 font-medium">Sem sensor real</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {installation.lastReadingLabel}:{' '}
              <span className="text-foreground tabular-nums font-medium">
                {installation.lastReadingSimulatedAt}
              </span>
            </p>
          </div>
        </div>
      </header>

      {/* ── Hero / página da instalação ───────────────────── */}
      <div className="bg-gradient-header">
        <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
          <div className="flex flex-wrap items-end justify-between gap-6">

            <div>
              {/* Localização */}
              <p className="text-[10px] uppercase tracking-[0.28em] text-white/60">
                Santana de Parnaíba · SP
              </p>

              {/* Nome da instalação */}
              <h1 className="mt-1 font-display text-4xl text-white sm:text-5xl">
                Hospital Santa Ana
              </h1>

              <div className="mt-3 flex flex-wrap items-center gap-3">
                <StatusBadge status={installation.status} />
                <MockDataBadge />
              </div>
            </div>

            {/* Métricas rápidas no hero */}
            <div className="flex flex-wrap gap-5">
              <HeroStat
                label="Consumo diário de referência"
                value={formatM3(installation.referenceDailyConsumptionM3)}
              />
              <HeroStat
                label="Capacidade monitorada"
                value="80.000 L"
              />
              <HeroStat
                label="Última leitura simulada"
                value={installation.lastReadingSimulatedAt}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Conteúdo principal ────────────────────────────── */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8 sm:py-10 space-y-8">
        {children}
      </main>

      {/* ── Footer ────────────────────────────────────────── */}
      <footer className="border-t border-border bg-card/60 backdrop-blur-sm">
        <div className="mx-auto max-w-7xl px-5 py-4 sm:px-8 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Building2 className="h-3.5 w-3.5" />
            <span>Hospital Santa Ana · Santana de Parnaíba</span>
          </div>
          <p className="text-[10px] text-muted-foreground italic">
            POC com dados simulados — sem integração com sensores reais nesta etapa.
          </p>
        </div>
      </footer>
    </div>
  );
}

// ── Helper: stat do hero ──────────────────────────────────────
function HeroStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-white backdrop-blur-sm">
      <p className="text-[9px] uppercase tracking-[0.2em] text-white/60">{label}</p>
      <p className="mt-1 text-lg font-bold tabular-nums">{value}</p>
    </div>
  );
}
