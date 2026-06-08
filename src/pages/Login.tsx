import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Droplets } from 'lucide-react';
import { isAuthenticated, login } from '../services/auth';

const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated()) navigate('/menu', { replace: true });
  }, [navigate]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    // Pequeno delay pra feedback visual
    await new Promise((r) => setTimeout(r, 400));

    const ok = login(username, password);
    if (ok) {
      navigate('/menu', { replace: true });
    } else {
      setError('Usuário ou senha inválidos.');
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-4 sm:p-8">
      <div className="w-full max-w-5xl overflow-hidden rounded-2xl bg-card shadow-card grid grid-cols-1 md:grid-cols-2 min-h-[600px]">
        {/* LEFT — Hero ilustrativo */}
        <aside className="relative hidden md:block bg-primary-deep">
          <div className="absolute inset-0 bg-gradient-to-br from-[hsl(222_75%_10%)] via-[hsl(220_70%_18%)] to-[hsl(215_65%_28%)]" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,hsl(var(--primary-glow)/0.35),transparent_55%)]" />

          {/* Bolhas decorativas */}
          <span className="absolute top-[12%] left-[20%] h-40 w-40 rounded-full bg-primary-glow/20 blur-3xl" />
          <span className="absolute bottom-[20%] right-[15%] h-52 w-52 rounded-full bg-primary-glow/15 blur-3xl" />

          {/* Brasão top-left */}
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

          {/* Welcome */}
          <div className="absolute bottom-12 left-8 right-8 text-primary-foreground z-10">
            <h2 className="text-4xl sm:text-5xl font-light tracking-[0.3em]">BEM-VINDO</h2>
            <p className="mt-3 text-sm text-primary-foreground/75 max-w-xs">
              Plataforma de telemetria de consumo de água do Hospital Santa Ana.
            </p>
          </div>

          {/* Ondas SVG no rodapé */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 overflow-hidden">
            <svg
              className="absolute inset-x-0 bottom-0 h-32 w-[200%] animate-wave-slow"
              viewBox="0 0 1200 120"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path
                d="M0,60 C200,100 400,20 600,60 C800,100 1000,20 1200,60 L1200,120 L0,120 Z"
                fill="hsl(var(--primary-glow) / 0.18)"
              />
            </svg>
          </div>
        </aside>

        {/* RIGHT — Form */}
        <section className="flex flex-col justify-between p-8 sm:p-14">
          <div>
            {/* Header mobile */}
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
                <label htmlFor="username" className="block text-sm text-foreground mb-1">
                  Usuário
                </label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                  className="w-full bg-transparent border-0 border-b border-input pb-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div>
                <div className="flex items-baseline justify-between mb-1">
                  <label htmlFor="password" className="block text-sm text-foreground">
                    Senha
                  </label>
                  <a href="#" className="text-xs font-semibold text-primary hover:text-primary-glow transition-colors">
                    Esqueceu a senha?
                  </a>
                </div>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
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
              <a href="#" className="font-semibold text-primary hover:text-primary-glow transition-colors">
                Solicitar acesso
              </a>
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
