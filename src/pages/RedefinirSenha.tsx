import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { verifyResetCode, resetPassword } from '../services/auth';
import { ApiError } from '../services/api';
import { validatePassword } from '../lib/password';

type Step = 'code' | 'newpass';

export default function RedefinirSenha() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const identifierFromState = (location.state as { identifier?: string } | null)?.identifier ?? '';

  const [identifier, setIdentifier] = useState(identifierFromState);
  const [code, setCode]             = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [step, setStep]             = useState<Step>('code');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [success, setSuccess]       = useState(false);

  const pwResult = newPassword ? validatePassword(newPassword, undefined, identifier) : null;

  async function onVerifyCode(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await verifyResetCode(identifier, code.trim());
      setStep('newpass');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Código inválido ou expirado.');
    } finally {
      setSubmitting(false);
    }
  }

  async function onReset(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const validation = validatePassword(newPassword, undefined, identifier);
    if (!validation.valid) {
      setError(validation.errors[0]);
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword(identifier, code.trim(), newPassword);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro ao redefinir senha.');
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-secondary p-4">
        <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10 text-center space-y-4">
          <p className="text-2xl font-semibold text-foreground">Senha redefinida!</p>
          <p className="text-sm text-muted-foreground">
            Sua senha foi atualizada com sucesso.
          </p>
          <button
            onClick={() => navigate('/', { replace: true })}
            className="mt-4 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground hover:bg-primary-glow"
          >
            Ir para o login
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-md bg-card rounded-2xl shadow-card p-10">
        {step === 'code' ? (
          <>
            <h1 className="text-3xl font-semibold text-foreground">Inserir código</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Digite o código de 6 dígitos enviado para seu email.
            </p>

            <form className="mt-8 space-y-6" onSubmit={onVerifyCode}>
              {!identifierFromState && (
                <div>
                  <label className="block text-sm text-foreground mb-1">Usuário ou email</label>
                  <input
                    type="text"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    required
                    className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm text-foreground mb-1">Código</label>
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
                {submitting ? 'Verificando...' : 'Próximo'}
              </button>
            </form>
          </>
        ) : (
          <>
            <h1 className="text-3xl font-semibold text-foreground">Nova senha</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Crie uma nova senha segura para sua conta.
            </p>

            <form className="mt-8 space-y-6" onSubmit={onReset}>
              <div>
                <label className="block text-sm text-foreground mb-1">Nova senha</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  autoFocus
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
                {submitting ? 'Salvando...' : 'Redefinir senha'}
              </button>
            </form>
          </>
        )}

        <p className="mt-6 text-center text-sm text-muted-foreground">
          <Link to="/" className="font-semibold text-primary hover:text-primary-glow">
            Voltar ao login
          </Link>
        </p>
      </div>
    </main>
  );
}
