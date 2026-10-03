/** 时间格式化工具（全站共用）。 */

/** ISO 时间 → 本地 "YYYY-MM-DD HH:mm:ss"；无效/空值显示 "-"。 */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 毫秒时长 → 人读格式（如 "1.2s" / "350ms"）。 */
export function fmtDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '-'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}
