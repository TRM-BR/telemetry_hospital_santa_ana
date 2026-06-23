import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { forgotPassword } from '../services/auth';

export default function EsqueciSenha() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await forgotPassword(identifier);
    } finally {
      // Always show "sent" (anti-enumeration)
      setSent(true);
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-secondary p-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10 text-center space-y-4">
          <p className="text-2xl font-semibold text-foreground">Código enviado</p>
          <p className="text-sm text-muted-foreground">
            Se o identificador for válido, um código foi enviado para o email cadastrado.
          </p>
          <button
            onClick={() => navigate('/redefinir-senha', { state: { identifier } })}
            className="mt-4 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary-glow"
          >
            Inserir código
          </button>
          <p className="text-sm">
            <Link to="/" className="text-primary hover:text-primary-glow font-semibold">
              Voltar ao login
            </Link>
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10">
        <h1 className="text-3xl font-semibold text-foreground">Recuperar senha</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Informe seu usuário ou email para receber um código de recuperação.
        </p>

        <form className="mt-8 space-y-6" onSubmit={onSubmit}>
          <div>
            <label className="block text-sm text-foreground mb-1">Usuário ou email</label>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft transition-smooth hover:bg-primary-glow disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {submitting ? 'Enviando...' : 'Enviar código'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link to="/" className="font-semibold text-primary hover:text-primary-glow">
            Voltar ao login
          </Link>
        </p>
      </div>
    </main>
  );
}
