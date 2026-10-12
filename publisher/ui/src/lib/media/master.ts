/**
 * Browser port of engines/motion/render/master_audio.py: gain to −14 LUFS integrated, lookahead limiter so the true
 * peak is ≤ −1 dBTP. Sample-aligned (output length = input length). Pure; no I/O.
 */
import { integratedLoudness, truePeakDb } from './loudness'
import type { PcmAudio } from './wav'

export const TARGET_LUFS = -14
export const TRUE_PEAK_MAX = -1

/** scipy.ndimage 'reflect' boundary: … c b a | a b c … */
function reflect(i: number, n: number): number {
  let k = i
  while (k < 0 || k >= n) k = k < 0 ? -k - 1 : 2 * n - k - 1
  return k
}

/** scipy.ndimage.minimum_filter1d(x, size) with an odd size (centred window), mode 'reflect'. */
export function minimumFilter(x: Float64Array, size: number): Float64Array {
  const n = x.length
  const half = (size - 1) / 2
  const out = new Float64Array(n)
  // Monotonic deque over the padded sequence p[j] = x[reflect(j - half)], j = 0 … n + size - 2.
  const at = (j: number) => x[reflect(j - half, n)] as number
  const deque: number[] = []
  let head = 0
  for (let j = 0; j < n + size - 1; j++) {
    const v = at(j)
    while (deque.length > head && at(deque[deque.length - 1] as number) >= v) deque.pop()
    deque.push(j)
    const start = j - size + 1
    if ((deque[head] as number) < start) head++
    if (start >= 0) out[start] = at(deque[head] as number)
  }
  return out
}

/** scipy.ndimage.uniform_filter1d(x, size), mode 'reflect': window [i − size//2, i + size − size//2 − 1]. */
export function uniformFilter(x: Float64Array, size: number): Float64Array {
  const n = x.length
  const before = Math.floor(size / 2)
  const out = new Float64Array(n)
  let sum = 0
  for (let k = -before; k < size - before; k++) sum += x[reflect(k, n)] as number
  for (let i = 0; i < n; i++) {
    out[i] = sum / size
    sum += (x[reflect(i + size - before, n)] as number) - (x[reflect(i - before, n)] as number)
  }
  return out
}

/** The limiter: per-sample gain so |x| ≤ ceil, held over ±3 ms, smoothed, 80 ms release. */
export function limit(channels: Float64Array[], ceil: number, rate: number): Float64Array[] {
  const n = channels[0]?.length ?? 0
  const look = Math.floor(0.003 * rate)
  const need = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    let m = 0
    for (const ch of channels) m = Math.max(m, Math.abs(ch[i] as number))
    need[i] = Math.min(1, ceil / Math.max(m, 1e-9))
  }
  const g = uniformFilter(minimumFilter(need, 2 * look + 1), look)
  const rel = Math.exp(-1 / (0.08 * rate))
  const gain = new Float64Array(n)
  let cur = 1
  for (let i = 0; i < n; i++) {
    const gi = g[i] as number
    cur = gi < cur ? gi : gi + (cur - gi) * rel
    gain[i] = cur
  }
  return channels.map((ch) => ch.map((v, i) => v * (gain[i] as number)))
}

export interface MasterResult {
  audio: PcmAudio
  lufs: number
  truePeakDbtp: number
  ceilingDb: number
}

/**
 * master_audio.py main(): four gain + limit passes; lower the ceiling by 0.5 dB until true peak ≤ `truePeakMax`
 * (default −1 dBTP, as master_audio.py) or the ceiling reaches −6 dB.
 */
export function master(input: PcmAudio, truePeakMax = TRUE_PEAK_MAX): MasterResult {
  const rate = input.sampleRate
  const y = input.channels.map((ch) => Float64Array.from(ch))
  let ceilDb = -1.5
  for (;;) {
    let out: Float64Array[] = y
    for (let pass = 0; pass < 4; pass++) {
      const L = integratedLoudness(out, rate)
      if (!Number.isFinite(L)) throw new Error('The mix is silent; nothing to master.')
      const k = 10 ** ((TARGET_LUFS - L) / 20)
      out = limit(out.map((ch) => ch.map((v) => v * k)), 10 ** (ceilDb / 20), rate)
    }
    const lufs = integratedLoudness(out, rate)
    const tp = truePeakDb(out)
    if (tp <= truePeakMax || ceilDb <= -6) {
      return { audio: { sampleRate: rate, channels: out.map((ch) => Float32Array.from(ch)) }, lufs, truePeakDbtp: tp, ceilingDb: ceilDb }
    }
    ceilDb -= 0.5
  }
}
