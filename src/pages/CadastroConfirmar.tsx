import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { registerConfirm } from '../services/auth';
import { ApiError } from '../services/api';

export default function CadastroConfirmar() {
  const location  = useLocation();
  const emailFromState = (location.state as { email?: string } | null)?.email ?? '';

  const [email, setEmail]   = useState(emailFromState);
  const [code, setCode]     = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await registerConfirm(email, code.trim());
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Código inválido ou expirado.');
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-secondary p-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10 text-center space-y-4">
          <p className="text-2xl font-semibold text-foreground">Cadastro enviado!</p>
          <p className="text-sm text-muted-foreground">
            Email confirmado. Seu cadastro aguarda aprovação de um administrador.
            Você receberá um email quando for aprovado.
          </p>
          <Link to="/" className="inline-block mt-4 text-sm font-semibold text-primary hover:text-primary-glow">
            Voltar ao login
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10">
        <h1 className="text-3xl font-semibold text-foreground">Confirmar email</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Digite o código de 6 dígitos enviado para seu email.
        </p>

        <form className="mt-8 space-y-6" onSubmit={onSubmit}>
          {!emailFromState && (
            <div>
              <label className="block text-sm text-foreground mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
              />
            </div>
          )}

          <div>
            <label className="block text-sm text-foreground mb-1">Código de confirmação</label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
              required
              autoFocus
              placeholder="000000"
              className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors tracking-[0.5em]"
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={submitting || code.length !== 6}
            className="w-full rounded-lg bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft transition-smooth hover:bg-primary-glow disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? 'Verificando...' : 'Confirmar'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link to="/cadastro" className="text-primary hover:text-primary-glow font-semibold">
            Novo código
          </Link>
          {' · '}
          <Link to="/" className="text-primary hover:text-primary-glow font-semibold">
            Login
          </Link>
        </p>
      </div>
    </main>
  );
}
