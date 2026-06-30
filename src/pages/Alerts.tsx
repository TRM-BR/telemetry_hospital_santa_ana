import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Droplets, Search, LayoutList, LayoutGrid, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { AlertsTable } from '@/components/alerts/AlertsTable';
import { AlertsGrid } from '@/components/alerts/AlertsGrid';
import { AlertDetailDialog } from '@/components/alerts/AlertDetailDialog';
import { useAlerts } from '@/hooks/useAlerts';
import type { AlertItem, AlertSeverity, AlertStatus } from '@/types/alerts';

type View = 'table' | 'grid';

function exportCsv(alerts: AlertItem[]) {
  const rows = [
    ['ID', 'Severidade', 'Status', 'Título', 'Instalação', 'Regra', 'Primeiro gatilho', 'Último gatilho', 'Resolvido em', 'Visto'],
    ...alerts.map((a) => [
      a.id,
      a.severity,
      a.status,
      `"${a.title.replace(/"/g, '""')}"`,
      a.installation_name,
      a.rule_key,
      a.first_triggered_at,
      a.last_triggered_at,
      a.resolved_at ?? '',
      a.viewed ? 'sim' : 'não',
    ]),
  ];
  const csv = rows.map((r) => r.join(',')).join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `alertas_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const SEVERITY_OPTS: { value: AlertSeverity | 'all'; label: string }[] = [
  { value: 'all',       label: 'Todas' },
  { value: 'critical',  label: 'Crítico' },
  { value: 'attention', label: 'Atenção' },
  { value: 'info',      label: 'Info' },
];

const STATUS_OPTS: { value: AlertStatus | 'all'; label: string }[] = [
  { value: 'all',      label: 'Todos' },
  { value: 'active',   label: 'Ativos' },
  { value: 'resolved', label: 'Resolvidos' },
];

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 shadow-soft">
      <p className={cn('text-3xl font-bold tabular-nums', color)}>{value}</p>
      <p className="text-[11px] text-muted-foreground mt-1">{label}</p>
    </div>
  );
}

const Alerts = () => {
  const navigate = useNavigate();
  const { data: alerts = [], isLoading } = useAlerts();

  const [query, setQuery]     = useState('');
  const [severity, setSeverity] = useState<AlertSeverity | 'all'>('all');
  const [status, setStatus]   = useState<AlertStatus | 'all'>('all');
  const [view, setView]       = useState<View>('table');
  const [selected, setSelected] = useState<AlertItem | null>(null);

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return alerts.filter((a) => {
      if (severity !== 'all' && a.severity !== severity) return false;
      if (status !== 'all' && a.status !== status) return false;
      if (q && !a.title.toLowerCase().includes(q) && !a.description.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [alerts, query, severity, status]);

  const total    = alerts.length;
  const critical = alerts.filter((a) => a.severity === 'critical').length;
  const attention = alerts.filter((a) => a.severity === 'attention').length;
  const resolved = alerts.filter((a) => a.status === 'resolved').length;

  return (
    <div className="min-h-screen w-full bg-secondary">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar
          </button>

          <div className="flex items-center gap-3 text-primary">
            <img
              src="/brasao_santana_de_parnaiba.webp"
              alt="Brasão"
              className="h-10 w-10 object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight hidden sm:block">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Santana de Parnaíba</p>
              <p className="text-[12px] font-semibold text-foreground">Alertas</p>
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
        {/* Título */}
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Hospital Santa Ana</p>
          <h1 className="mt-1 text-3xl font-bold text-foreground">Alertas e eventos</h1>
          <p className="mt-1 text-sm text-muted-foreground">Vazamentos, picos de consumo e eventos do dispositivo.</p>
        </div>

        {/* Stats */}
        {!isLoading && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Total"     value={total}    color="text-foreground" />
            <StatCard label="Críticos"  value={critical}  color="text-destructive" />
            <StatCard label="Atenção"   value={attention} color="text-amber-600" />
            <StatCard label="Resolvidos" value={resolved} color="text-emerald-600" />
          </div>
        )}

        {/* Controles */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Busca */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Buscar alertas…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Filtro severidade */}
          <div className="flex rounded-lg border border-border bg-card overflow-hidden text-xs">
            {SEVERITY_OPTS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setSeverity(value)}
                className={cn(
                  'px-3 py-2 font-medium transition-colors',
                  severity === value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Filtro status */}
          <div className="flex rounded-lg border border-border bg-card overflow-hidden text-xs">
            {STATUS_OPTS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatus(value)}
                className={cn(
                  'px-3 py-2 font-medium transition-colors',
                  status === value
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Toggle view */}
          <div className="flex rounded-lg border border-border bg-card overflow-hidden">
            <button
              type="button"
              onClick={() => setView('table')}
              className={cn(
                'p-2 transition-colors',
                view === 'table' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
              title="Tabela"
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView('grid')}
              className={cn(
                'p-2 transition-colors',
                view === 'grid' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
              title="Cards"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>

          {/* Export */}
          <Button variant="outline" size="sm" onClick={() => exportCsv(filtered)} className="gap-1.5">
            <Download className="h-3.5 w-3.5" />
            CSV
          </Button>
        </div>

        {/* Contagem filtrada */}
        <p className="text-[11px] text-muted-foreground">
          {isLoading ? 'Carregando…' : `${filtered.length} resultado${filtered.length !== 1 ? 's' : ''}`}
        </p>

        {/* Lista */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-16 rounded-2xl bg-card border border-border animate-pulse" />
            ))}
          </div>
        ) : view === 'table' ? (
          <AlertsTable alerts={filtered} onSelect={setSelected} />
        ) : (
          <AlertsGrid alerts={filtered} onSelect={setSelected} />
        )}
      </main>

      <AlertDetailDialog
        alert={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
      />
    </div>
  );
};

export default Alerts;
