/**
 * The Studio's motion chunk (lazy-loaded; other screens never download Remotion): in-browser preview and export of a
 * Scalargame episode with the motion engine's own kit, mirroring engines/motion/render/render.sh:
 *
 *   1. the composition's audio mix as WAV (render.sh: `remotion render --codec=wav`);
 *   2. mastered to −14 LUFS / ≤ −1 dBTP (master_audio.py, ported);
 *   3. the video with the kit's audio silenced and the mastered mix as its only track (H.264 + AAC 48 kHz stereo);
 *   4. the AAC priming measured on this device and skipped by an edit list, the last frame's duration set
 *      (render.sh: fdk-AAC with the priming edit list);
 *   5. QA as render.mjs (lib/media/deliveryQa.ts) plus audio sync; the cover still at infoComplete + 0.5 s.
 *
 * Assets come from the Pi (GET /api/assets/motion/…): `window.remotion_staticBase` is set before the kit loads,
 * because the kit resolves its fonts at import.
 */
import { Audio } from '@remotion/media'
import { canRenderMediaOnWeb, renderMediaOnWeb, renderStillOnWeb, type RenderMediaOnWebProgress } from '@remotion/web-renderer'
import type { ComponentType } from 'react'
import { audioOffset, blackSegments, containerMeasures, deliveryErrors, type DeliveryMeasures } from '../lib/media/deliveryQa'
import { integratedLoudness, silenceStarts, truePeakDb } from '../lib/media/loudness'
import { master, type MasterResult } from '../lib/media/master'
import { fixBrowserMp4, readMp4 } from '../lib/media/mp4'
import { readWav, writeWavFloat } from '../lib/media/wav'
import { coverFrame, type JobInput } from './bundle'
import type { ExportedFiles } from './webPackage'

export const FPS = 30
export const WIDTH = 1080
export const HEIGHT = 1920
const SAMPLE_RATE = 48000
const LICENSE = 'free-license' // Remotion Free License: individuals qualify (remotion.dev/docs/license/faq).
const VIDEO_BITRATE = 3_000_000
const AUDIO_BITRATE = 192_000
const DELAY_RENDER_TIMEOUT = 120_000
const MAX_COVER_BYTES = 2_000_000

type Props = JobInput['props']
type Kit = typeof import('./kit')

let kitPromise: Promise<Kit> | null = null

/** Load the kit once, with staticFile() pointed at `staticBase` (the Pi's versioned asset URL; null in the dev harness). */
export function loadKit(staticBase: string | null): Promise<Kit> {
  if (!kitPromise) {
    if (staticBase) window.remotion_staticBase = staticBase
    kitPromise = import('./kit')
  }
  return kitPromise
}

function composition(component: ComponentType<Props>, props: Props) {
  return {
    id: 'LibraryEpisode',
    component,
    durationInFrames: props.durationInFrames,
    fps: FPS,
    width: WIDTH,
    height: HEIGHT,
  }
}

/** The episode with its own audio silenced and one mastered track instead (step 3). */
function masteredEpisode(kit: Kit) {
  const Mastered = (props: Props & { masteredSrc: string }) => {
    const { masteredSrc, ...episode } = props
    const Episode = kit.LibraryEpisode as unknown as ComponentType<Props>
    return (
      <>
        <Episode {...episode} sfxVolume={0} music={{ ...episode.music, volume: 0 }} />
        <Audio src={masteredSrc} />
      </>
    )
  }
  return Mastered
}

export interface DeviceCheck {
  canExport: boolean
  issues: string[]
}

export async function checkDevice(): Promise<DeviceCheck> {
  try {
    const result = await canRenderMediaOnWeb({ container: 'mp4', videoCodec: 'h264', audioCodec: 'aac', width: WIDTH, height: HEIGHT, videoBitrate: VIDEO_BITRATE, audioBitrate: AUDIO_BITRATE })
    return { canExport: result.canRender, issues: result.issues.map((i) => i.message) }
  } catch (error) {
    return { canExport: false, issues: [error instanceof Error ? error.message : String(error)] }
  }
}

async function sha256Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data as BufferSource)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function decode(bytes: ArrayBuffer): Promise<Float32Array[]> {
  const ctx = new OfflineAudioContext({ numberOfChannels: 2, length: SAMPLE_RATE, sampleRate: SAMPLE_RATE })
  const buffer = await ctx.decodeAudioData(bytes.slice(0))
  return Array.from({ length: buffer.numberOfChannels }, (_, c) => buffer.getChannelData(c))
}

/** Mean luma (0–255) of the exported video at 10 fps, from the encoded file (qa_media.py's black-frame sampling). */
async function frameLumas(mp4: Blob, duration: number, signal: AbortSignal | undefined): Promise<number[]> {
  const url = URL.createObjectURL(mp4)
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.preload = 'auto'
  video.src = url
  try {
    await new Promise<void>((resolve, reject) => {
      video.onloadeddata = () => resolve()
      video.onerror = () => reject(new Error('This browser cannot play the exported video back for checking.'))
    })
    const canvas = document.createElement('canvas')
    canvas.width = 54
    canvas.height = 96
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) throw new Error('No 2D canvas for frame checks.')
    const out: number[] = []
    for (let t = 0; t < duration - 0.001; t += 0.1) {
      if (signal?.aborted) throw new DOMException('Export cancelled.', 'AbortError')
      await new Promise<void>((resolve) => {
        video.onseeked = () => resolve()
        video.currentTime = Math.min(t + 0.001, duration - 0.001)
      })
      ctx.drawImage(video, 0, 0, 54, 96)
      const px = ctx.getImageData(0, 0, 54, 96).data
      let sum = 0
      for (let i = 0; i < px.length; i += 4) sum += 0.299 * (px[i] ?? 0) + 0.587 * (px[i + 1] ?? 0) + 0.114 * (px[i + 2] ?? 0)
      out.push(sum / (px.length / 4))
    }
    return out
  } finally {
    video.removeAttribute('src')
    video.load()
    URL.revokeObjectURL(url)
  }
}

export type ExportPhase = 'audio' | 'master' | 'video' | 'qa' | 'cover'

export interface ExportResult {
  mp4: Blob
  cover: Blob
  files: ExportedFiles
  measures: DeliveryMeasures
  errors: string[]
  master: Pick<MasterResult, 'lufs' | 'truePeakDbtp' | 'ceilingDb'>
  primingSamples: number
  seconds: number
}

/** Export one episode (steps above). Throws on cancel or a failure that leaves no file; QA failures are in `errors`. */
export async function exportEpisode(
  job: JobInput,
  opts: { staticBase: string | null; signal?: AbortSignal; onProgress?: (phase: ExportPhase, fraction: number) => void; allowHtmlInCanvas?: boolean },
): Promise<ExportResult> {
  const started = performance.now()
  const kit = await loadKit(opts.staticBase)
  const props = job.props
  const progress = opts.onProgress ?? (() => undefined)
  const common = {
    licenseKey: LICENSE,
    delayRenderTimeoutInMilliseconds: DELAY_RENDER_TIMEOUT,
    allowHtmlInCanvas: opts.allowHtmlInCanvas ?? false,
    ...(opts.signal ? { signal: opts.signal } : {}),
  }

  // 1. The mix as the composition plays it.
  progress('audio', 0)
  const wav = await renderMediaOnWeb({
    ...common,
    composition: composition(kit.LibraryEpisode as unknown as ComponentType<Props>, props),
    inputProps: props,
    container: 'wav',
    sampleRate: SAMPLE_RATE,
    onProgress: (p: RenderMediaOnWebProgress) => progress('audio', p.progress),
  } as never)
  const mix = readWav(await (await wav.getBlob()).arrayBuffer())

  // 2. Mastering.
  progress('master', 0)
  const mastered = master(mix)
  const masteredSrc = URL.createObjectURL(new Blob([writeWavFloat(mastered.audio)], { type: 'audio/wav' }))
  try {
    // 3. Video with the mastered mix.
    progress('video', 0)
    const Mastered = masteredEpisode(kit)
    const rendered = await renderMediaOnWeb({
      ...common,
      composition: composition(Mastered as unknown as ComponentType<Props>, props),
      inputProps: { ...props, masteredSrc },
      container: 'mp4',
      videoCodec: 'h264',
      audioCodec: 'aac',
      videoBitrate: VIDEO_BITRATE,
      audioBitrate: AUDIO_BITRATE,
      sampleRate: SAMPLE_RATE,
      keyframeIntervalInSeconds: 2,
      onProgress: (p: RenderMediaOnWebProgress) => progress('video', p.progress),
    } as never)
    const raw = await (await rendered.getBlob()).arrayBuffer()

    // 4. Priming (decoded audio vs the mastered mix) → edit list; last frame duration.
    progress('qa', 0)
    const primingSamples = audioOffset(mastered.audio.channels, await decode(raw))
    if (primingSamples < 0) throw new Error(`The encoded audio starts ${-primingSamples} samples early; this device's AAC encoder is not supported.`)
    const fixed = fixBrowserMp4(new Uint8Array(raw), { fps: FPS, frames: props.durationInFrames, primingSamples })
    const mp4 = new Blob([fixed as BlobPart], { type: 'video/mp4' })

    // 5. QA of the delivered file.
    progress('qa', 0.3)
    const decoded = await decode(fixed.buffer.slice(fixed.byteOffset, fixed.byteOffset + fixed.byteLength) as ArrayBuffer)
    progress('qa', 0.5)
    const container = containerMeasures(readMp4(fixed), fixed.byteLength)
    const lumas = await frameLumas(mp4, props.durationInFrames / FPS, opts.signal)
    const measures: DeliveryMeasures = {
      ...container,
      loudnessLufs: Math.round(integratedLoudness(decoded, SAMPLE_RATE) * 10) / 10,
      truePeakDbtp: Math.round(truePeakDb(decoded) * 10) / 10,
      silenceStarts: silenceStarts(decoded, SAMPLE_RATE),
      blackSegments: blackSegments(lumas),
      audioOffsetSamples: audioOffset(mastered.audio.channels, decoded),
    }
    const errors = deliveryErrors(measures, { frames: props.durationInFrames, fps: FPS })

    progress('cover', 0)
    const still = await renderStillOnWeb({
      ...common,
      composition: composition(kit.LibraryEpisode as unknown as ComponentType<Props>, props),
      inputProps: props,
      frame: coverFrame(job, FPS),
    } as never)
    const cover = await still.blob({ format: 'jpeg', quality: 0.9 })
    if (cover.size > MAX_COVER_BYTES) errors.push(`cover ${cover.size} bytes`)
    progress('cover', 1)

    return {
      mp4,
      cover,
      measures,
      errors,
      master: { lufs: mastered.lufs, truePeakDbtp: mastered.truePeakDbtp, ceilingDb: mastered.ceilingDb },
      primingSamples,
      seconds: Math.round((performance.now() - started) / 100) / 10,
      files: {
        createdAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
        video: {
          sha256: await sha256Hex(fixed),
          bytes: fixed.byteLength,
          durationSeconds: container.durationSeconds,
          width: container.width ?? 0,
          height: container.height ?? 0,
          fps: container.fps ?? '',
          videoCodec: container.videoCodec ?? '',
          audioCodec: container.audioCodec ?? '',
        },
        cover: { sha256: await sha256Hex(await cover.arrayBuffer()), bytes: cover.size },
      },
    }
  } finally {
    URL.revokeObjectURL(masteredSrc)
  }
}
