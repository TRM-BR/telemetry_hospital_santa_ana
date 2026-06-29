import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';
import type { EnergyDashboardResponse } from '../types/energy';

export function useEnergyDashboard(slug: string, hours: number) {
  return useQuery({
    queryKey: ['energy-dashboard', slug, hours],
    queryFn: () =>
      api<EnergyDashboardResponse>(
        `/installations/${slug}/energy/dashboard?hours=${hours}`,
      ),
    refetchInterval: 30_000,
    staleTime: 25_000,
    enabled: slug.length > 0,
  });
}
