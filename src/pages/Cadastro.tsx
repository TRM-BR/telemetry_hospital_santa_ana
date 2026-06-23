import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '../services/auth';
import { ApiError } from '../services/api';
import { validatePassword } from '../lib/password';

export default function Cadastro() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]   = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const pwResult = password ? validatePassword(password, username, email) : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const validation = validatePassword(password, username, email);
    if (!validation.valid) {
      setError(validation.errors[0]);
      return;
    }

    setSubmitting(true);
    try {
      await register(username, email, password);
      setSuccess(true);
      setTimeout(() => navigate('/cadastro/confirmar', { state: { email } }), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro ao solicitar acesso. Tente novamente.');
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-secondary p-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10 text-center space-y-4">
          <p className="text-2xl font-semibold text-foreground">Código enviado!</p>
          <p className="text-sm text-muted-foreground">
            Se o email for válido, um código de confirmação foi enviado para <strong>{email}</strong>.
            Redirecionando...
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10">
        <h1 className="text-3xl font-semibold text-foreground">Solicitar acesso</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Após o cadastro, um aprovador irá liberar seu acesso.
        </p>

        <form className="mt-8 space-y-6" onSubmit={onSubmit}>
          <div>
            <label className="block text-sm text-foreground mb-1">Usuário</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
            />
          </div>

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

          <div>
            <label className="block text-sm text-foreground mb-1">Senha</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
            />
            {pwResult && !pwResult.valid && (
              <ul className="mt-2 space-y-0.5">
                {pwResult.errors.map((e, i) => (
                  <li key={i} className="text-xs text-destructive">• {e}</li>
                ))}
              </ul>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft transition-smooth hover:bg-primary-glow disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? 'Enviando...' : 'Solicitar acesso'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Já tem conta?{' '}
          <Link to="/" className="font-semibold text-primary hover:text-primary-glow">
            Entrar
          </Link>
        </p>
      </div>
    </main>
  );
}
