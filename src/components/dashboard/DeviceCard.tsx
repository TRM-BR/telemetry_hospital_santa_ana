import type { ReactNode } from 'react';
import { Gauge, Droplets, Battery, SignalHigh, Activity, Clock } from 'lucide-react';
import type { DashDevice } from '../../types/telemetry';
import { cn } from '../../lib/cn';

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

export function deviceLabel(d: DashDevice): string {
  return d.label ?? `Remota ${d.imei.slice(-4)}`;
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

export function DeviceCard({ device, signalLost }: { device: DashDevice; signalLost?: boolean }) {
  const l = device.latest;
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Remota</p>
          <h3 className="mt-1 text-lg font-semibold text-foreground">{deviceLabel(device)}</h3>
          <p className="text-[11px] text-muted-foreground tabular-nums">IMEI {device.imei}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold',
              device.active
                ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30'
                : 'bg-muted text-muted-foreground border-border',
            )}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {device.active ? 'Ativa' : 'Sem sinal'}
          </span>
          {signalLost && (
            <p className="text-[11px] text-muted-foreground text-right">
              Último receb.:{' '}
              <span className="text-foreground tabular-nums">{fmtDateTime(device.last_seen_utc)}</span>
            </p>
          )}
        </div>
      </div>

      <div className={cn('grid grid-cols-2 gap-3', signalLost && 'opacity-60 grayscale')}>
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

export { fmtDateTime };
export default DeviceCard;
