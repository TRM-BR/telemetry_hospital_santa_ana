import { useQuery } from '@tanstack/react-query';
import { ApiError, api } from '../services/api';
import { buildEnergyDashboardMock } from '../mocks/energyDashboardMock';
import type { EnergyDashboardResponse } from '../types/energy';

const MOCKS_ENABLED = import.meta.env.VITE_ENABLE_MOCKS === 'true';
const DEV_MOCK_FALLBACK_ENABLED = import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCKS !== 'false';

function hasEnergyData(data: EnergyDashboardResponse): boolean {
  return (
    data.last_seen_utc !== null ||
    data.bars.length > 0 ||
    Object.values(data.series).some((points) => points.length > 0)
  );
}

async function fetchEnergyDashboard(slug: string, hours: number): Promise<EnergyDashboardResponse> {
  if (MOCKS_ENABLED) {
    return buildEnergyDashboardMock(slug, hours);
  }

  try {
    const data = await api<EnergyDashboardResponse>(
      `/installations/${slug}/energy/dashboard?hours=${hours}`,
    );

    if (DEV_MOCK_FALLBACK_ENABLED && !hasEnergyData(data)) {
      return buildEnergyDashboardMock(slug, hours);
    }

    return data;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      throw err;
    }

    if (DEV_MOCK_FALLBACK_ENABLED) {
      return buildEnergyDashboardMock(slug, hours);
    }

    throw err;
  }
}

export function useEnergyDashboard(slug: string, hours: number) {
  return useQuery({
    queryKey: ['energy-dashboard', slug, hours],
    queryFn: () => fetchEnergyDashboard(slug, hours),
    refetchInterval: 30_000,
    staleTime: 25_000,
    enabled: slug.length > 0,
  });
}
