/**
 * Browser QA of an exported episode against the contract v1 delivery spec, with the same bar and messages as
 * engines/motion/pipeline/render.mjs qa(): H.264 yuv420p 1080×1920 30/1, AAC 48 kHz stereo, duration within 0.05 s,
 * ≤ 24,000,000 bytes, fast start, −14 ± 2 LUFS, true peak ≤ −1 dBTP, no black segments, no silence gaps. Browser
 * exports also need their audio in sync with the mastered mix (the AAC priming edit list). A failed check blocks
 * the upload. Pure; the caller measures (mp4.ts, loudness.ts, frame sampling) and passes the numbers in.
 */
import type { Mp4Info } from './mp4'

export const MAX_BYTES = 24_000_000

export interface DeliveryMeasures {
  bytes: number
  durationSeconds: number
  width: number | null
  height: number | null
  fps: string | null
  videoCodec: string | null
  pixFmt: string | null
  audioCodec: string | null
  audioSampleRate: number | null
  audioChannels: number | null
  fastStart: boolean
  loudnessLufs: number
  truePeakDbtp: number
  silenceStarts: number[]
  blackSegments: number
  /** Decoded audio vs the mastered mix, in samples (0 = in sync). */
  audioOffsetSamples: number
}

function gcd(a: number, b: number): number {
  return b ? gcd(b, a % b) : a
}

/** Container facts in ffprobe's vocabulary (fps = frames ÷ stream duration, as avg_frame_rate). */
export function containerMeasures(info: Mp4Info, bytes: number): Pick<DeliveryMeasures, 'bytes' | 'durationSeconds' | 'width' | 'height' | 'fps' | 'videoCodec' | 'pixFmt' | 'audioCodec' | 'audioSampleRate' | 'audioChannels' | 'fastStart'> {
  const v = info.tracks.find((t) => t.handler === 'vide')
  const a = info.tracks.find((t) => t.handler === 'soun')
  let fps: string | null = null
  if (v && v.duration > 0) {
    const num = v.sampleCount * v.timescale
    const g = gcd(num, v.duration)
    fps = `${num / g}/${v.duration / g}`
  }
  return {
    bytes,
    durationSeconds: Math.round((info.movieDuration / info.movieTimescale) * 1000) / 1000,
    width: v?.width ?? null,
    height: v?.height ?? null,
    fps,
    videoCodec: v ? (v.codec === 'avc1' || v.codec === 'avc3' ? 'h264' : v.codec) : null,
    pixFmt: v ? (v.chromaFormat === 1 && v.bitDepth === 8 ? 'yuv420p' : `chroma${v.chromaFormat ?? '?'}/${v.bitDepth ?? '?'}bit`) : null,
    audioCodec: a ? (a.codec === 'mp4a' && a.audioObjectType === 2 ? 'aac' : `${a.codec}/${a.audioObjectType ?? '?'}`) : null,
    audioSampleRate: a?.sampleRate ?? null,
    audioChannels: a?.channels ?? null,
    fastStart: info.fastStart,
  }
}

/** Plain-language failures; empty = passes. */
export function deliveryErrors(m: DeliveryMeasures, expected: { frames: number; fps: number }): string[] {
  const errors: string[] = []
  if (m.videoCodec !== 'h264' || m.pixFmt !== 'yuv420p') errors.push(`video ${m.videoCodec}/${m.pixFmt}`)
  if (m.width !== 1080 || m.height !== 1920) errors.push(`size ${m.width}x${m.height}`)
  if (m.fps !== `${expected.fps}/1`) errors.push(`fps ${m.fps}`)
  if (m.audioCodec !== 'aac' || m.audioSampleRate !== 48000 || m.audioChannels !== 2)
    errors.push(`audio ${m.audioCodec} ${m.audioSampleRate} ${m.audioChannels}ch`)
  if (Math.abs(m.durationSeconds - expected.frames / expected.fps) > 0.05) errors.push(`duration ${m.durationSeconds}s`)
  if (m.bytes > MAX_BYTES) errors.push(`size ${m.bytes} > ${MAX_BYTES}`)
  if (!m.fastStart) errors.push('not fast-start')
  if (!(Math.abs(m.loudnessLufs + 14) <= 2)) errors.push(`loudness ${m.loudnessLufs.toFixed(1)} LUFS outside −14 ± 2`)
  if (!(m.truePeakDbtp <= -1)) errors.push(`true peak ${m.truePeakDbtp.toFixed(1)} dBTP above −1`)
  if (m.blackSegments) errors.push(`${m.blackSegments} black segment(s)`)
  if (m.silenceStarts.length) errors.push(`silence at ${m.silenceStarts.join(', ')}s`)
  if (m.audioOffsetSamples !== 0) errors.push(`audio out of sync by ${m.audioOffsetSamples} samples`)
  return errors
}

/** Black segments from per-frame mean luma (0–255) sampled at 10 fps: a run ≥ 0.2 s below 5 % (qa_media.py). */
export function blackSegments(lumaMeans: readonly number[]): number {
  let segments = 0
  let run = 0
  for (const luma of lumaMeans) {
    run = luma < 0.05 * 255 ? run + 1 : 0
    if (run === 2) segments++
  }
  return segments
}

/**
 * Offset of `decoded` against `reference` in samples (positive = decoded is late), searched in [−maxLag, maxLag] over
 * the first `window` samples of the mono mixes: the AAC priming before the edit list, 0 after it.
 */
export function audioOffset(reference: readonly ArrayLike<number>[], decoded: readonly ArrayLike<number>[], maxLag = 4096, window = 96000): number {
  const mono = (chs: readonly ArrayLike<number>[], n: number) => {
    const out = new Float64Array(n)
    for (const ch of chs) for (let i = 0; i < n && i < ch.length; i++) out[i] = (out[i] as number) + (ch[i] as number) / chs.length
    return out
  }
  const n = Math.min(window, reference[0]?.length ?? 0)
  const ref = mono(reference, n)
  const dec = mono(decoded, n + maxLag)
  let best = 0
  let bestErr = Infinity
  for (let lag = -maxLag; lag <= maxLag; lag++) {
    let err = 0
    for (let i = Math.max(0, -lag); i < n && i + lag < dec.length; i++) {
      const d = (dec[i + lag] as number) - (ref[i] as number)
      err += d * d
      if (err >= bestErr) break
    }
    if (err < bestErr) {
      bestErr = err
      best = lag
    }
  }
  return best
}
