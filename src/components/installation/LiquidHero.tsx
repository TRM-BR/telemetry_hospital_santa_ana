import type { ReactNode } from 'react';

interface LiquidHeroProps {
  children: ReactNode;
}

/**
 * Hero líquido — fundo azul profundo com ondas SVG animadas e gradiente.
 */
export function LiquidHero({ children }: LiquidHeroProps) {
  return (
    <section className="relative overflow-hidden rounded-3xl bg-primary-deep text-primary-foreground shadow-card">
      <div className="absolute inset-0 bg-gradient-to-br from-[hsl(222_75%_10%)] via-[hsl(220_70%_18%)] to-[hsl(215_65%_28%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom_right,hsl(var(--primary-glow)/0.28),transparent_55%)]" />

      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <span className="absolute top-[-30px] left-[18%] h-32 w-32 rounded-full bg-primary-glow/20 blur-3xl" />
        <span className="absolute bottom-[30%] right-[12%] h-40 w-40 rounded-full bg-primary-glow/15 blur-3xl" />
      </div>

      <div className="relative z-10 px-8 py-12 sm:px-14 sm:py-16">{children}</div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 overflow-hidden">
        <svg
          className="absolute inset-x-0 bottom-0 h-28 w-[200%] animate-wave-slow"
          viewBox="0 0 1200 120"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M0,60 C200,100 400,20 600,60 C800,100 1000,20 1200,60 L1200,120 L0,120 Z"
            fill="hsl(var(--primary-glow) / 0.28)"
          />
        </svg>
        <svg
          className="absolute inset-x-0 bottom-0 h-28 w-[200%] animate-wave-fast"
          viewBox="0 0 1200 120"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M0,80 C150,40 350,110 600,70 C850,30 1050,100 1200,80 L1200,120 L0,120 Z"
            fill="hsl(var(--primary-glow) / 0.45)"
          />
        </svg>
      </div>
    </section>
  );
}

export default LiquidHero;
