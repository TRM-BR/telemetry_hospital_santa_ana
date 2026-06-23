import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import type { PendingUser } from '../types/auth';

async function fetchPending(): Promise<PendingUser[]> {
  return api<PendingUser[]>('/users/pending');
}

async function vote(userId: number, action: 'approve' | 'reject', note?: string) {
  return api(`/users/pending/${userId}/${action}`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  });
}

export default function Aprovacoes() {
  const queryClient = useQueryClient();
  const [note, setNote] = useState<Record<number, string>>({});

  const { data: pending = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['users', 'pending'],
    queryFn: fetchPending,
    refetchInterval: 30_000,
  });

  const { mutate: castVote, isPending: voting } = useMutation({
    mutationFn: ({ userId, action, note }: { userId: number; action: 'approve' | 'reject'; note?: string }) =>
      vote(userId, action, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users', 'pending'] });
    },
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-6 w-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-8 text-center text-destructive">
        Erro ao carregar usuários pendentes.{' '}
        <button onClick={() => void refetch()} className="underline">Tentar novamente</button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Aprovações</h1>
          <p className="text-sm text-muted-foreground">
            Cadastros aguardando liberação de acesso.
          </p>
        </div>
        <button
          onClick={() => void refetch()}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Atualizar
        </button>
      </div>

      {pending.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-10 text-center space-y-2">
          <Clock className="h-8 w-8 text-muted-foreground mx-auto" />
          <p className="text-muted-foreground text-sm">Nenhum cadastro pendente.</p>
        </div>
      ) : (
        <ul className="space-y-4">
          {pending.map((u) => (
            <li key={u.id} className="rounded-xl border border-border bg-card p-5 space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-semibold text-foreground">{u.username}</p>
                  <p className="text-sm text-muted-foreground">{u.email ?? '—'}</p>
                </div>
                <span className="text-xs rounded-full bg-amber-500/10 text-amber-600 px-2 py-0.5 font-medium">
                  Pendente
                </span>
              </div>

              <div>
                <label className="block text-xs text-muted-foreground mb-1">
                  Observação (opcional)
                </label>
                <input
                  type="text"
                  maxLength={200}
                  value={note[u.id] ?? ''}
                  onChange={(e) => setNote((prev) => ({ ...prev, [u.id]: e.target.value }))}
                  placeholder="Motivo da decisão..."
                  className="w-full bg-transparent border-b border-input pb-1 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => castVote({ userId: u.id, action: 'approve', note: note[u.id] })}
                  disabled={voting}
                  className="flex items-center gap-2 rounded-lg bg-green-600 hover:bg-green-700 px-4 py-2 text-sm font-semibold text-white transition-colors disabled:opacity-60"
                >
                  <CheckCircle className="h-4 w-4" />
                  Aprovar
                </button>
                <button
                  onClick={() => castVote({ userId: u.id, action: 'reject', note: note[u.id] })}
                  disabled={voting}
                  className="flex items-center gap-2 rounded-lg bg-destructive hover:bg-destructive/80 px-4 py-2 text-sm font-semibold text-white transition-colors disabled:opacity-60"
                >
                  <XCircle className="h-4 w-4" />
                  Rejeitar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
