import { useEffect, useRef, useState } from 'react';
import { Droplets, Battery, SignalHigh, Activity } from 'lucide-react';
import { ReservoirGauge } from './ReservoirGauge';
import { deviceLabel } from './DeviceCard';
import type { DashDevice } from '../../types/telemetry';

function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toFixed(digits);
}

type EstadoKey = 'Confortável' | 'Atenção' | 'Crítico' | 'Sem leitura';

function getEstado(pct: number | null | undefined): EstadoKey {
  if (pct == null) return 'Sem leitura';
  if (pct >= 70) return 'Confortável';
  if (pct >= 40) return 'Atenção';
  return 'Crítico';
}

const ESTADO_CLASS: Record<EstadoKey, string> = {
  'Confortável': 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  'Atenção':     'bg-amber-500/10 text-amber-600 border-amber-500/30',
  'Crítico':     'bg-destructive/10 text-destructive border-destructive/30',
  'Sem leitura': 'bg-muted text-muted-foreground border-border',
};

function useCountUp(target: number, duration = 800) {
  const [value, setValue] = useState(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const start = performance.now();
    const from = 0;
    function tick(now: number) {
      const t = Math.min(1, (now - start) / duration);
      const ease = 1 - Math.pow(1 - t, 3);
      setValue(from + (target - from) * ease);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return value;
}

function Chip({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5 rounded-xl border border-border bg-secondary/50 px-3 py-2">
      <span className="text-primary">{icon}</span>
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</span>
      <span className="ml-auto text-xs font-bold text-foreground tabular-nums">{value}</span>
    </div>
  );
}

export function LevelGaugeCard({ device }: { device: DashDevice }) {
  const l = device.latest;
  const pct = l.level_pct ?? 0;
  const animatedPct = useCountUp(pct);
  const estado = getEstado(l.level_pct);

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft animate-drop-in flex flex-col">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Nível atual</p>
          <h3 className="mt-1 text-base font-semibold text-foreground">{deviceLabel(device)}</h3>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${ESTADO_CLASS[estado]}`}>
          {estado}
        </span>
      </div>

      <div className="flex items-center justify-center gap-6 flex-1 py-2">
        <ReservoirGauge level={pct} width={90} height={140} />
        <div className="text-center">
          <p
            className="text-5xl font-black text-foreground tabular-nums leading-none"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {l.level_pct == null ? '—' : `${animatedPct.toFixed(1)}`}
          </p>
          <p className="text-xl font-semibold text-primary mt-1">%</p>
          {l.level_m != null && (
            <p className="text-xs text-muted-foreground mt-2 tabular-nums">
              {fmt(l.level_m, 2)} m
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Chip icon={<Battery className="h-3.5 w-3.5" />} label="Bateria" value={l.battery_v != null ? `${fmt(l.battery_v, 2)} V` : '—'} />
        <Chip icon={<SignalHigh className="h-3.5 w-3.5" />} label="Sinal" value={l.signal != null ? `${fmt(l.signal, 0)} dBm` : '—'} />
        <Chip icon={<Activity className="h-3.5 w-3.5" />} label="Corrente" value={l.current_ma != null ? `${fmt(l.current_ma, 2)} mA` : '—'} />
        <Chip icon={<Droplets className="h-3.5 w-3.5" />} label="Nível" value={l.level_m != null ? `${fmt(l.level_m, 2)} m` : '—'} />
      </div>
    </div>
  );
}

export default LevelGaugeCard;
