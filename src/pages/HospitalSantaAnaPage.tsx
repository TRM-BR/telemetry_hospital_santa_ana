/**
 * HospitalSantaAnaPage
 *
 * Página principal da POC — Hospital Santa Ana.
 * Todos os dados vêm do mock centralizado em src/mocks/hospitalSantaAnaMock.ts.
 * Nenhuma chamada de API — POC com dados simulados.
 */

import {
  Droplets,
  Gauge,
  Hourglass,
  Clock,
  Database,
  AlertTriangle,
  Activity,
  BarChart3,
} from 'lucide-react';

import { hospitalSantaAnaMock as mock } from '../mocks/hospitalSantaAnaMock';
import { AppShell } from '../components/layout/AppShell';
import { KpiCard } from '../components/dashboard/KpiCard';
import { HospitalChart } from '../components/dashboard/HospitalChart';
import { AlertsList } from '../components/dashboard/AlertsList';
import { HospitalHydraulicScheme } from '../components/topology/HospitalHydraulicScheme';

export function HospitalSantaAnaPage() {
  const { installation, tankGroups, series, alerts } = mock;
  const g1 = tankGroups[0];
  const g2 = tankGroups[1];

  // Spark data para KPI cards
  const sparkG1 = series.levelG1Hourly.map((p) => p.value);
  const sparkG2 = series.levelG2Hourly.map((p) => p.value);
  const sparkFlow = series.estimatedFlowM3Hourly.map((p) => p.value);

  // Autonomia estimada mínima entre os grupos
  const minAutonomy = Math.min(g1.estimatedAutonomyHours, g2.estimatedAutonomyHours);

  // Status label
  const statusLabel: Record<typeof installation.status, string> = {
    normal:    'Operação normal',
    attention: 'Atenção',
    critical:  'Crítico',
  };

  return (
    <AppShell installation={installation}>

      {/* ── Seção: Esquema hidráulico ──────────────────────── */}
      <section aria-labelledby="schema-title">
        <div className="mb-3">
          <h2 id="schema-title" className="text-base font-semibold text-foreground">
            Topologia da instalação
          </h2>
          <p className="text-[12px] text-muted-foreground">
            Grupo 1 e Grupo 2 — caixas superiores de 10.000 L — são os pontos monitorados.
            Os reservatórios de recalque (40.000 L) aparecem apenas como contexto hidráulico.
          </p>
        </div>
        <HospitalHydraulicScheme data={mock} />
      </section>

      {/* ── Seção: KPIs ───────────────────────────────────── */}
      <section aria-labelledby="kpi-title">
        <h2 id="kpi-title" className="mb-4 text-base font-semibold text-foreground">
          Indicadores operacionais
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            icon={Droplets}
            label="Nível · Grupo 1"
            value={g1.levelPct}
            suffix="%"
            spark={sparkG1}
            delayMs={0}
            tone="default"
          />
          <KpiCard
            icon={Droplets}
            label="Nível · Grupo 2"
            value={g2.levelPct}
            suffix="%"
            spark={sparkG2}
            delayMs={60}
            tone="accent"
          />
          <KpiCard
            icon={Database}
            label="Capacidade monitorada"
            value={installation.monitoredCapacityLiters}
            suffix="L"
            delayMs={120}
          />
          <KpiCard
            icon={Gauge}
            label="Consumo estimado 24h"
            value={installation.referenceDailyConsumptionM3}
            suffix="m³"
            decimals={2}
            spark={sparkFlow}
            delayMs={180}
          />
          <KpiCard
            icon={Hourglass}
            label="Autonomia estimada"
            value={minAutonomy}
            suffix="h"
            delayMs={60}
          />
          <KpiCard
            icon={Clock}
            label="Última leitura simulada"
            textValue={installation.lastReadingSimulatedAt}
            delayMs={120}
          />
          <KpiCard
            icon={AlertTriangle}
            label="Alertas ativos"
            value={alerts.filter((a) => a.severity !== 'info').length}
            delayMs={180}
            tone={alerts.some((a) => a.severity === 'critical') ? 'danger' : 'accent'}
          />
          <KpiCard
            icon={Activity}
            label="Status geral"
            textValue={statusLabel[installation.status]}
            delayMs={240}
            tone={
              installation.status === 'critical'
                ? 'danger'
                : installation.status === 'attention'
                  ? 'accent'
                  : 'default'
            }
          />
        </div>
      </section>

      {/* ── Seção: Gráficos ───────────────────────────────── */}
      <section aria-labelledby="charts-title">
        <h2 id="charts-title" className="mb-4 text-base font-semibold text-foreground">
          Histórico simulado — últimas 24 horas
        </h2>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <HospitalChart
            title="Nível — Grupo 1"
            subtitle="4 caixas superiores de 10.000 L · sensor LV"
            unit="%"
            yDomain={[40, 100]}
            chartType="line"
            series={[{
              key: 'level',
              label: 'Nível G1',
              color: 'hsl(var(--primary))',
              data: series.levelG1Hourly,
            }]}
            badges={[{ label: 'Atual', value: `${g1.levelPct}%` }]}
            delayMs={80}
          />
          <HospitalChart
            title="Nível — Grupo 2"
            subtitle="4 caixas superiores de 10.000 L · sensor LV"
            unit="%"
            yDomain={[40, 100]}
            chartType="line"
            series={[{
              key: 'level',
              label: 'Nível G2',
              color: 'hsl(var(--accent))',
              data: series.levelG2Hourly,
            }]}
            badges={[{ label: 'Atual', value: `${g2.levelPct}%` }]}
            delayMs={160}
          />
          <HospitalChart
            title="Consumo / Vazão estimada"
            subtitle="Estimativa baseada na variação de nível · referência 46,11 m³/dia"
            unit="m³/h"
            yDomain={[0, 'auto']}
            chartType="area"
            series={[{
              key: 'flow',
              label: 'Vazão est.',
              color: 'hsl(var(--primary-glow))',
              data: series.estimatedFlowM3Hourly,
            }]}
            badges={[{
              label: 'Ref. 24h',
              value: `${installation.referenceDailyConsumptionM3} m³`,
            }]}
            delayMs={240}
          />

          {/* Alertas ao lado do terceiro gráfico */}
          <AlertsList alerts={alerts} />
        </div>
      </section>

      {/* ── Nota discreta sobre a POC ─────────────────────── */}
      <section>
        <div className="rounded-2xl border border-amber-400/30 bg-amber-50/60 px-5 py-4">
          <div className="flex items-start gap-3">
            <BarChart3 className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
            <div>
              <p className="text-sm font-semibold text-amber-800">
                POC com dados simulados
              </p>
              <p className="mt-0.5 text-[12px] text-amber-700">
                Todos os valores exibidos nesta tela são <strong>dados simulados</strong> para
                demonstração da solução. Não há integração com sensores reais, banco de dados
                ou API nesta etapa. Os gráficos e KPIs refletem um cenário realista construído
                a partir das especificações hidráulicas do Hospital Santa Ana (Santana de Parnaíba).
                O consumo diário de referência de <strong>46,11 m³/dia</strong> é extraído do
                projeto hidráulico da instalação.
              </p>
            </div>
          </div>
        </div>
      </section>

    </AppShell>
  );
}
