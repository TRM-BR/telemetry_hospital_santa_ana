import { useState, useEffect } from 'react';

/**
 * Anima um número de 0 até `target` usando ease-out cúbico.
 * Recria a animação sempre que `target` muda.
 */
export function useCountUp(target: number, duration = 900): number {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const start = performance.now();
    let raf: number;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // cubic ease-out
      setCurrent(target * eased);
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return current;
}
