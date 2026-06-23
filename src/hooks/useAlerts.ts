import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AlertItem } from '../types/alerts';
import { api } from '../services/api';

const QUERY_KEY = ['alerts'] as const;

const MOCKS_ENABLED = import.meta.env.VITE_ENABLE_MOCKS === 'true';

async function fetchAlerts(): Promise<AlertItem[]> {
  if (MOCKS_ENABLED) {
    const { mockAlerts } = await import('../mocks/alertsMock');
    return mockAlerts;
  }
  const json = await api<{ alerts?: AlertItem[] }>('/alerts?active_only=false');
  if (!Array.isArray(json?.alerts)) return [];
  return json.alerts;
}

async function setAlertViewed(id: string, viewed: boolean): Promise<void> {
  const method = viewed ? 'POST' : 'DELETE';
  await api(`/alerts/${id}/viewed`, { method });
}

export function useAlerts() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAlerts,
    staleTime: 30_000,
  });
}

export function useToggleAlertViewed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, viewed }: { id: string; viewed: boolean }) =>
      setAlertViewed(id, viewed),
    onMutate: async ({ id, viewed }) => {
      await qc.cancelQueries({ queryKey: QUERY_KEY });
      const prev = qc.getQueryData<AlertItem[]>(QUERY_KEY);
      qc.setQueryData<AlertItem[]>(QUERY_KEY, (old) =>
        old?.map((a) => (a.id === id ? { ...a, viewed } : a)) ?? [],
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUERY_KEY, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: QUERY_KEY }),
  });
}
