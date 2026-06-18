import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LogOut, Map as MapIcon, Activity, List as ListIcon, Droplets,
} from 'lucide-react';
import { installations } from '../mocks/hospitalSantaAnaMock';
import { getUsername, logout } from '../services/auth';
import { cn } from '../lib/cn';
import type { InstallationStatus } from '../types/telemetry';

const statusFilters: { id: InstallationStatus | 'all'; label: string }[] = [
  { id: 'all',     label: 'Todos' },
  { id: 'online',  label: 'Online' },
  { id: 'alert',   label: 'Alerta' },
  { id: 'offline', label: 'Offline' },
];

const MapPage = () => {
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [filter, setFilter] = useState<InstallationStatus | 'all'>('all');
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');
  const username = getUsername();

  const filtered = useMemo(
    () => (filter === 'all' ? installations : installations.filter((i) => i.status === filter)),
    [filter],
  );

  const counts = useMemo(
    () => ({
      total:   installations.length,
      online:  installations.filter((i) => i.status === 'online').length,
      alert:   installations.filter((i) => i.status === 'alert').length,
      offline: installations.filter((i) => i.status === 'offline').length,
    }),
    [],
  );

  return (
    <div className="h-screen overflow-hidden grid grid-cols-1 lg:grid-cols-[420px_1fr]">
      {/* ── LEFT — Painel ──────────────────────────────────── */}
      <aside className="relative flex flex-col h-full overflow-hidden border-r border-border bg-card">
        <div className="flex items-center justify-between px-7 pt-6">
          <div className="flex items-center gap-3 text-primary">
            <img
              src="/santana-coat.png"
              alt="Brasão de Santana de Parnaíba"
              className="h-14 w-14 object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">
                Santana de Parnaíba
              </p>
              <p className="text-[13px] font-semibold text-foreground">Telemetria Hídrica</p>
              {username && <p className="text-[11px] text-muted-foreground">Usuário: {username}</p>}
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate('/', { replace: true });
            }}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-[11px] font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sair
          </button>
        </div>

        <div className="px-7 pt-10">
          <h1 className="text-[44px] leading-[1.05] font-bold tracking-tight text-foreground">
            Monitor de
            <br />
            instalações
          </h1>
          <p className="mt-3 text-sm text-muted-foreground max-w-[320px]">
            Acompanhe o módulo de telemetria de água do Hospital Santa Ana em tempo real.
          </p>
        </div>

        <div className="px-7 pt-7">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-3">Status</p>
          <div className="flex flex-wrap gap-2">
            {statusFilters.map((f) => {
              const isActive = filter === f.id;
              return (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    'rounded-full px-4 py-1.5 text-xs font-medium transition-smooth border',
                    isActive
                      ? 'bg-primary text-primary-foreground border-primary shadow-soft'
                      : 'bg-transparent text-muted-foreground border-border hover:text-foreground hover:border-primary/40',
                  )}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="px-7 pt-6">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground mb-3">Visão geral</p>
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Online',  value: counts.online,  dot: 'bg-primary' },
              { label: 'Alerta',  value: counts.alert,   dot: 'bg-accent' },
              { label: 'Offline', value: counts.offline, dot: 'bg-destructive' },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border border-border bg-secondary/60 px-3 py-3">
                <div className="flex items-center gap-1.5">
                  <span className={cn('h-1.5 w-1.5 rounded-full', m.dot)} />
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{m.label}</span>
                </div>
                <p className="mt-1.5 text-2xl font-bold text-foreground tabular-nums">{m.value}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="px-7 pt-6 space-y-2">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setViewMode('map')}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-smooth border',
                viewMode === 'map'
                  ? 'bg-primary text-primary-foreground border-primary shadow-soft'
                  : 'bg-transparent text-muted-foreground border-border hover:text-foreground hover:border-primary/40',
              )}
            >
              <MapIcon className="h-4 w-4" />
              Mapa
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-smooth border',
                viewMode === 'list'
                  ? 'bg-primary text-primary-foreground border-primary shadow-soft'
                  : 'bg-transparent text-muted-foreground border-border hover:text-foreground hover:border-primary/40',
              )}
            >
              <ListIcon className="h-4 w-4" />
              Lista
            </button>
          </div>
        </div>

        <div className="flex-1" />

        <div className="px-7 pb-6 pt-6">
          <div className="flex items-center justify-center gap-2">
            <span className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Powered by</span>
            <span className="inline-flex items-center gap-1 font-display text-sm text-primary">
              <Droplets className="h-3.5 w-3.5" />
              Vector
            </span>
          </div>
        </div>
      </aside>

      {/* ── RIGHT — Mapa ou Lista ──────────────────────────── */}
      <section className="relative h-full overflow-hidden bg-secondary">
        {viewMode === 'map' ? (
          <>
            <img
              src="/guaratingueta-map.png"
              alt="Mapa Guaratinguetá"
              className="h-full w-full object-cover"
            />

            {/* Overlay top */}
            <div className="pointer-events-none absolute inset-x-0 top-0 p-5 flex items-start justify-between gap-4 z-[1000]">
              <div className="pointer-events-auto flex items-center gap-3">
                <div className="inline-flex items-center gap-2 rounded-full bg-card/90 backdrop-blur px-4 py-2 shadow-soft border border-border">
                  <MapIcon className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold text-foreground">Guaratinguetá, SP</span>
                </div>
              </div>

              <div className="pointer-events-auto flex items-center gap-3">
                <div className="hidden sm:flex items-center gap-5 rounded-full bg-card/90 backdrop-blur px-5 py-2 shadow-soft border border-border">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-sm font-bold text-foreground tabular-nums">{counts.total}</span>
                    <span className="text-[11px] text-muted-foreground">instalações</span>
                  </div>
                  <span className="h-3 w-px bg-border" />
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-sm font-bold text-foreground tabular-nums">{counts.online}</span>
                    <span className="text-[11px] text-muted-foreground">online</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Overlay bottom */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 p-5 flex items-end justify-end gap-4 z-[1000]">
              <div className="pointer-events-auto inline-flex items-center gap-2 rounded-full bg-card/95 backdrop-blur px-4 py-2 shadow-soft border border-border">
                <Activity className="h-3.5 w-3.5 text-primary" />
                <span className="text-[11px] text-muted-foreground">tempo real</span>
              </div>
            </div>
          </>
        ) : (
          <div className="h-full flex flex-col overflow-hidden">
            <div className="flex-1 overflow-y-auto">
              <div className="divide-y divide-border">
                {filtered.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-muted-foreground p-8">
                    <p>Nenhuma instalação encontrada</p>
                  </div>
                ) : (
                  filtered.map((installation) => (
                    <button
                      key={installation.id}
                      onClick={() => {
                        setSelectedId(installation.id);
                        navigate(`/instalacao/${installation.id}`);
                      }}
                      className={cn(
                        'w-full text-left px-4 py-3 sm:px-6 sm:py-4 transition-colors hover:bg-secondary/50 active:bg-secondary',
                        selectedId === installation.id && 'bg-primary/10 border-l-4 border-primary',
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-foreground text-sm sm:text-base truncate">
                            {installation.name}
                          </p>
                          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5 truncate">
                            {installation.address}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <span
                            className={cn(
                              'h-2 w-2 rounded-full',
                              installation.status === 'online'  ? 'bg-primary'
                                : installation.status === 'alert' ? 'bg-accent'
                                : 'bg-destructive',
                            )}
                          />
                          <span className="text-xs font-medium text-muted-foreground capitalize">
                            {installation.status === 'online' ? 'Online'
                              : installation.status === 'alert' ? 'Alerta' : 'Offline'}
                          </span>
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default MapPage;
