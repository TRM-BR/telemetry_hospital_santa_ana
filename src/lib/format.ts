/** Formata número com separador PT-BR */
export function formatNumber(n: number, decimals = 0): string {
  return n.toLocaleString('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Formata litros como "80.000 L" */
export function formatLiters(liters: number): string {
  return `${formatNumber(liters)} L`;
}

/** Formata m³ com 2 casas */
export function formatM3(m3: number): string {
  return `${formatNumber(m3, 2)} m³`;
}

/** Formata percentual */
export function formatPct(pct: number): string {
  return `${formatNumber(pct, 1)}%`;
}
