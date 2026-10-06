/** 数字格式辅助：公差常用 µm 级，固定 4 位有效小数；份额按百分比。 */
export function fmt(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (v === 0) return '0';
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(2);
  if (abs >= 10) return v.toFixed(3);
  return v.toFixed(digits);
}

export function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return (v * 100).toFixed(1) + '%';
}
