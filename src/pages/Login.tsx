import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Droplets } from 'lucide-react';
import { isAuthenticated, login } from '../services/auth';
import { ApiError } from '../services/api';
import cityImage from '../assets/child-water.jpg';

const STATUS_MESSAGES: Record<string, string> = {
  pending:              'Seu cadastro ainda está aguardando aprovação.',
  rejected:             'Cadastro não aprovado. Entre em contato com o administrador.',
  inactive:             'Conta desativada. Entre em contato com o administrador.',
  pending_email:        'Confirme seu email antes de fazer login.',
  pending_email_change: 'Seu email precisa ser atualizado. Entre em contato com o administrador.',
};

function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    const msg = err.message.toLowerCase();
    for (const [key, label] of Object.entries(STATUS_MESSAGES)) {
      if (msg.includes(key) || msg.includes(label.toLowerCase().slice(0, 15))) {
        return label;
      }
    }
    if (err.status === 403) return err.message;
    return 'Usuário ou senha inválidos.';
  }
  return 'Erro de conexão. Verifique a rede e tente novamente.';
}

const Login = () => {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword]   = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated()) navigate('/menu', { replace: true });
  }, [navigate]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await login(identifier, password);
      navigate('/menu', { replace: true });
    } catch (err) {
      setError(friendlyError(err));
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-5xl overflow-hidden rounded-2xl bg-card shadow-card grid grid-cols-1 md:grid-cols-2 min-h-[600px]">
        {/* LEFT — Hero ilustrativo */}
        <aside className="relative hidden md:block bg-primary-deep">
          <img
            src={cityImage}
            alt="Criança brincando com água"
            className="absolute inset-0 h-full w-full object-cover"
            width={1536}
            height={1024}
          />
          <div className="absolute inset-0 bg-gradient-to-b from-primary-deep/60 via-primary-deep/20 to-primary-deep/80" />

          <div className="absolute top-8 left-8 flex items-center gap-3 text-primary-foreground z-10">
            <img
              src="/santana-coat.png"
              alt="Brasão de Santana de Parnaíba"
              className="h-16 w-16 object-contain drop-shadow-md"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight">
              <p className="text-[10px] uppercase tracking-[0.2em] text-primary-foreground/70">
                Prefeitura de Santana de Parnaíba
              </p>
              <p className="text-sm font-semibold tracking-wide">Telemetria Hídrica</p>
            </div>
          </div>

          <div className="absolute bottom-12 left-8 right-8 text-primary-foreground z-10">
            <h2 className="text-4xl sm:text-5xl font-light tracking-[0.3em]">BEM-VINDO</h2>
            <p className="mt-3 text-sm text-primary-foreground/75 max-w-xs">
              Plataforma de telemetria de consumo de água do Hospital Santa Ana.
            </p>
          </div>

        </aside>

        {/* RIGHT — Form */}
        <section className="flex flex-col justify-between p-8 sm:p-14">
          <div>
            <div className="md:hidden flex items-center gap-3 mb-8 text-primary">
              <img
                src="/santana-coat.png"
                alt="Brasão"
                className="h-14 w-14 object-contain"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
              <div className="leading-tight">
                <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                  Santana de Parnaíba
                </p>
                <p className="text-sm font-semibold">Telemetria Hídrica</p>
              </div>
            </div>

            <h1 className="text-3xl sm:text-4xl font-semibold text-foreground">Login</h1>
            <p className="mt-2 text-sm text-muted-foreground">Acesse o painel de telemetria</p>

            <form className="mt-10 space-y-7" onSubmit={onSubmit}>
              <div>
                <label htmlFor="identifier" className="block text-sm text-foreground mb-1">
                  Usuário ou email
                </label>
                <input
                  id="identifier"
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  autoFocus
                  autoComplete="username"
                  className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div>
                <div className="flex items-baseline justify-between mb-1">
                  <label htmlFor="password" className="block text-sm text-foreground">
                    Senha
                  </label>
                  <Link
                    to="/esqueci-senha"
                    className="text-xs font-semibold text-primary hover:text-primary-glow transition-colors"
                  >
                    Esqueceu a senha?
                  </Link>
                </div>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground shadow-soft transition-smooth hover:bg-primary-glow active:translate-y-px disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {submitting ? 'Entrando...' : 'Entrar'}
              </button>
            </form>
          </div>

          <div className="mt-10 space-y-6">
            <p className="text-center text-sm text-muted-foreground">
              Não tem uma conta?{' '}
              <Link
                to="/cadastro"
                className="font-semibold text-primary hover:text-primary-glow transition-colors"
              >
                Solicitar acesso
              </Link>
            </p>

            <div className="flex items-center justify-center gap-2 pt-4 border-t border-border">
              <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Powered by
              </span>
              <span className="inline-flex items-center gap-1 font-display text-base text-primary">
                <Droplets className="h-4 w-4" />
                Vector
              </span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
};

export default Login;
