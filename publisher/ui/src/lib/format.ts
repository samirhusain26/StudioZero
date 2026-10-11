export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return 'unknown'
  if (bytes < 1000) return `${bytes} B`
  const units = ['kB', 'MB', 'GB', 'TB']
  let value = bytes / 1000
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`
}

export function shortHash(sha: string | null | undefined, length = 8): string {
  return sha ? sha.slice(0, length) : '—'
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return 'unknown'
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds - m * 60)
  return `${m} min ${s} s`
}

export function formatFps(fps: string | null | undefined): string {
  if (!fps) return 'unknown'
  const [a, b] = fps.split('/').map(Number)
  if (!a || !b) return fps
  const value = a / b
  return `${Number.isInteger(value) ? value : value.toFixed(2)} fps`
}

const PLATFORM_NAMES: Record<string, string> = {
  instagram: 'Instagram', facebook: 'Facebook', threads: 'Threads', x: 'X',
  youtube: 'YouTube', bluesky: 'Bluesky', tiktok: 'TikTok',
}

export function platformName(platform: string): string {
  return PLATFORM_NAMES[platform] ?? platform
}

export function titleCase(text: string): string {
  return text.replace(/[-_]/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}
