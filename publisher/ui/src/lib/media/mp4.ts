/**
 * Minimal ISO-BMFF (MP4) reading and the two fixes a browser export needs before it meets the delivery spec
 * (contract v1; engines/motion/render/render.sh does the same with ffmpeg and fdk-AAC):
 *
 * - the last video sample gets the frame duration (the web encoder writes 0, so the stream reads 1 frame short and
 *   ffprobe's average frame rate is off), with track and movie durations to match;
 * - the audio track gets an edit list that skips the AAC encoder priming (without one the audio plays late, e.g.
 *   2112 samples = 44 ms) and ends exactly at the video's end.
 *
 * Pure functions over bytes; no I/O.
 */

export interface Box {
  type: string
  start: number
  size: number
  header: number
}

export interface TrackInfo {
  handler: string
  codec: string
  timescale: number
  duration: number
  sampleCount: number
  /** stts entries [count, delta]. */
  stts: [number, number][]
  /** elst entries [segmentDuration (movie timescale), mediaTime (track timescale)]. */
  edits: [number, number][]
  width?: number
  height?: number
  avcProfile?: number
  /** 1 = 4:2:0 (from avcC; profiles without the extension imply 4:2:0). */
  chromaFormat?: number
  bitDepth?: number
  channels?: number
  sampleRate?: number
  /** MPEG-4 audio object type from esds (2 = AAC LC). */
  audioObjectType?: number
}

export interface Mp4Info {
  topLevel: string[]
  /** moov comes before mdat (fast start). */
  fastStart: boolean
  movieTimescale: number
  movieDuration: number
  tracks: TrackInfo[]
}

const u32 = (b: Uint8Array, o: number) => ((b[o] ?? 0) * 0x1000000 + ((b[o + 1] ?? 0) << 16) + ((b[o + 2] ?? 0) << 8) + (b[o + 3] ?? 0)) >>> 0
const u16 = (b: Uint8Array, o: number) => ((b[o] ?? 0) << 8) | (b[o + 1] ?? 0)
const i32 = (b: Uint8Array, o: number) => u32(b, o) | 0
function u64(b: Uint8Array, o: number): number {
  return u32(b, o) * 0x100000000 + u32(b, o + 4)
}
function put32(b: Uint8Array, o: number, v: number) {
  b[o] = (v >>> 24) & 255
  b[o + 1] = (v >>> 16) & 255
  b[o + 2] = (v >>> 8) & 255
  b[o + 3] = v & 255
}
function put64(b: Uint8Array, o: number, v: number) {
  put32(b, o, Math.floor(v / 0x100000000))
  put32(b, o + 4, v >>> 0)
}
const type = (b: Uint8Array, o: number) => String.fromCharCode(b[o] ?? 0, b[o + 1] ?? 0, b[o + 2] ?? 0, b[o + 3] ?? 0)

export class Mp4Error extends Error {}

/** Child boxes in [start, end). Refuses malformed sizes. */
export function boxes(b: Uint8Array, start: number, end: number): Box[] {
  const out: Box[] = []
  let o = start
  while (o + 8 <= end) {
    let size = u32(b, o)
    let header = 8
    if (size === 1) {
      size = u64(b, o + 8)
      header = 16
    } else if (size === 0) size = end - o
    if (size < header || o + size > end) throw new Mp4Error(`bad box size at ${o}`)
    out.push({ type: type(b, o + 4), start: o, size, header })
    o += size
  }
  return out
}

function child(b: Uint8Array, box: Box, name: string, skip = 0): Box | null {
  return boxes(b, box.start + box.header + skip, box.start + box.size).find((x) => x.type === name) ?? null
}

function path(b: Uint8Array, box: Box | null, names: string[]): Box | null {
  let cur = box
  for (const n of names) cur = cur ? child(b, cur, n) : null
  return cur
}

function moovOf(b: Uint8Array): Box {
  const moov = boxes(b, 0, b.length).find((x) => x.type === 'moov')
  if (!moov) throw new Mp4Error('no moov box')
  return moov
}

/** mvhd/mdhd/tkhd: version 1 uses 64-bit times. Returns [timescaleOffset, durationOffset, durationBytes]. */
function timeFields(b: Uint8Array, box: Box, kind: 'mvhd' | 'mdhd' | 'tkhd'): { timescale: number | null; durationAt: number; wide: boolean } {
  const v = b[box.start + box.header] ?? 0
  const base = box.start + box.header + 4
  if (kind === 'tkhd') return { timescale: null, durationAt: v === 1 ? base + 8 + 8 + 4 + 4 : base + 4 + 4 + 4 + 4, wide: v === 1 }
  if (v === 1) return { timescale: u32(b, base + 16), durationAt: base + 20, wide: true }
  return { timescale: u32(b, base + 8), durationAt: base + 12, wide: false }
}

function readDuration(b: Uint8Array, at: number, wide: boolean): number {
  return wide ? u64(b, at) : u32(b, at)
}

function writeDuration(b: Uint8Array, at: number, wide: boolean, value: number) {
  if (wide) put64(b, at, value)
  else put32(b, at, value)
}

/** ES_Descriptor (3) → DecoderConfigDescriptor (4) → DecoderSpecificInfo (5): its first 5 bits (2 = AAC LC). */
function audioObjectType(b: Uint8Array, start: number, end: number): number | undefined {
  const descriptor = (o: number): { tag: number; body: number; end: number } => {
    const tag = b[o] ?? 0
    let size = 0
    let k = o + 1
    for (let i = 0; i < 4; i++, k++) {
      const byte = b[k] ?? 0
      size = (size << 7) | (byte & 0x7f)
      if ((byte & 0x80) === 0) {
        k++
        break
      }
    }
    return { tag, body: k, end: Math.min(k + size, end) }
  }
  const es = descriptor(start)
  if (es.tag !== 3) return undefined
  const flags = b[es.body + 2] ?? 0
  let o = es.body + 3
  if (flags & 0x80) o += 2
  if (flags & 0x40) o += 1 + (b[o] ?? 0)
  if (flags & 0x20) o += 2
  const config = descriptor(o)
  if (config.tag !== 4) return undefined
  const specific = descriptor(config.body + 13)
  return specific.tag === 5 && specific.body < specific.end ? (b[specific.body] ?? 0) >> 3 : undefined
}

function trackInfo(b: Uint8Array, trak: Box): TrackInfo {
  const mdia = child(b, trak, 'mdia')
  const mdhd = path(b, mdia, ['mdhd'])
  const hdlr = path(b, mdia, ['hdlr'])
  const stbl = path(b, mdia, ['minf', 'stbl'])
  const stsd = path(b, stbl, ['stsd'])
  const stts = path(b, stbl, ['stts'])
  const stsz = path(b, stbl, ['stsz'])
  if (!mdhd || !hdlr || !stsd || !stts || !stsz) throw new Mp4Error('incomplete track')
  const t = timeFields(b, mdhd, 'mdhd')
  const info: TrackInfo = {
    handler: type(b, hdlr.start + hdlr.header + 8),
    codec: '',
    timescale: t.timescale ?? 0,
    duration: readDuration(b, t.durationAt, t.wide),
    sampleCount: u32(b, stsz.start + stsz.header + 8),
    stts: [],
    edits: [],
  }
  const n = u32(b, stts.start + stts.header + 4)
  for (let i = 0; i < n; i++) info.stts.push([u32(b, stts.start + stts.header + 8 + 8 * i), u32(b, stts.start + stts.header + 12 + 8 * i)])
  const elst = path(b, trak, ['edts', 'elst'])
  if (elst) {
    const v = b[elst.start + elst.header] ?? 0
    const count = u32(b, elst.start + elst.header + 4)
    for (let i = 0; i < count; i++) {
      const o = elst.start + elst.header + 8 + i * (v === 1 ? 20 : 12)
      info.edits.push(v === 1 ? [u64(b, o), u64(b, o + 8)] : [u32(b, o), i32(b, o + 4)])
    }
  }
  const entry = boxes(b, stsd.start + stsd.header + 8, stsd.start + stsd.size)[0]
  if (entry) {
    info.codec = entry.type
    const body = entry.start + entry.header
    if (info.handler === 'vide') {
      info.width = u16(b, body + 24)
      info.height = u16(b, body + 26)
      const avcC = boxes(b, body + 78, entry.start + entry.size).find((x) => x.type === 'avcC')
      if (avcC) {
        const a = avcC.start + avcC.header
        info.avcProfile = b[a + 1] ?? 0
        // High-profile avcC carries chroma_format_idc and bit depths after the parameter sets.
        let o = a + 5
        const sps = (b[o] ?? 0) & 31
        o += 1
        for (let i = 0; i < sps; i++) o += 2 + u16(b, o)
        const pps = b[o] ?? 0
        o += 1
        for (let i = 0; i < pps; i++) o += 2 + u16(b, o)
        if ([100, 110, 122, 144].includes(info.avcProfile) && o + 3 < avcC.start + avcC.size) {
          info.chromaFormat = (b[o] ?? 0) & 3
          info.bitDepth = ((b[o + 1] ?? 0) & 7) + 8
        } else {
          info.chromaFormat = 1
          info.bitDepth = 8
        }
      }
    } else if (info.handler === 'soun') {
      info.channels = u16(b, body + 16)
      info.sampleRate = u32(b, body + 24) / 65536
      const esds = boxes(b, body + 28, entry.start + entry.size).find((x) => x.type === 'esds')
      const aot = esds ? audioObjectType(b, esds.start + esds.header + 4, esds.start + esds.size) : undefined
      if (aot !== undefined) info.audioObjectType = aot
    }
  }
  return info
}

export function readMp4(bytes: Uint8Array): Mp4Info {
  const top = boxes(bytes, 0, bytes.length)
  const moov = moovOf(bytes)
  const mvhd = child(bytes, moov, 'mvhd')
  if (!mvhd) throw new Mp4Error('no mvhd box')
  const t = timeFields(bytes, mvhd, 'mvhd')
  const names = top.map((x) => x.type)
  const mdat = names.indexOf('mdat')
  return {
    topLevel: names,
    fastStart: mdat >= 0 && names.indexOf('moov') < mdat,
    movieTimescale: t.timescale ?? 0,
    movieDuration: readDuration(bytes, t.durationAt, t.wide),
    tracks: boxes(bytes, moov.start + moov.header, moov.start + moov.size)
      .filter((x) => x.type === 'trak')
      .map((x) => trackInfo(bytes, x)),
  }
}

function elstBox(segmentDuration: number, mediaTime: number): Uint8Array {
  const out = new Uint8Array(36)
  put32(out, 0, 36)
  out.set([101, 100, 116, 115], 4) // edts
  put32(out, 8, 28)
  out.set([101, 108, 115, 116], 12) // elst
  put32(out, 16, 0) // version 0, flags
  put32(out, 20, 1)
  put32(out, 24, segmentDuration)
  put32(out, 28, mediaTime)
  put32(out, 32, 0x00010000) // media rate 1.0
  return out
}

export interface FixOptions {
  fps: number
  /** Video frames delivered (the composition's durationInFrames). */
  frames: number
  /** Encoder priming to skip at the start of the audio track, in audio samples. */
  primingSamples: number
}

/**
 * The delivery fixes (see the file comment). Returns new bytes; the input is not changed. Uses the `free` box after
 * moov for the inserted edit list when it is large enough, otherwise shifts mdat and every chunk offset.
 */
export function fixBrowserMp4(input: Uint8Array, opts: FixOptions): Uint8Array {
  const info = readMp4(input)
  if (!info.fastStart) throw new Mp4Error('expected moov before mdat')
  const vi = info.tracks.findIndex((t) => t.handler === 'vide')
  const ai = info.tracks.findIndex((t) => t.handler === 'soun')
  if (vi < 0) throw new Mp4Error('no video track')
  const video = info.tracks[vi] as TrackInfo
  const delta = video.timescale / opts.fps
  if (!Number.isInteger(delta)) throw new Mp4Error(`video timescale ${video.timescale} is not a multiple of ${opts.fps}`)
  if (video.sampleCount !== opts.frames) throw new Mp4Error(`video has ${video.sampleCount} frames, expected ${opts.frames}`)
  const videoMediaDuration = opts.frames * delta
  const movieDuration = Math.round((opts.frames / opts.fps) * info.movieTimescale)

  const bytes = input.slice()
  const moov = moovOf(bytes)
  const traks = boxes(bytes, moov.start + moov.header, moov.start + moov.size).filter((x) => x.type === 'trak')
  // Video: every sample lasts one frame (rewrite the stts deltas in place; entry count unchanged).
  const vtrak = traks[vi] as Box
  const stts = path(bytes, vtrak, ['mdia', 'minf', 'stbl', 'stts']) as Box
  const entries = u32(bytes, stts.start + stts.header + 4)
  for (let i = 0; i < entries; i++) put32(bytes, stts.start + stts.header + 12 + 8 * i, delta)
  const vmdhd = path(bytes, vtrak, ['mdia', 'mdhd']) as Box
  const vm = timeFields(bytes, vmdhd, 'mdhd')
  writeDuration(bytes, vm.durationAt, vm.wide, videoMediaDuration)
  const vtkhd = child(bytes, vtrak, 'tkhd') as Box
  const vt = timeFields(bytes, vtkhd, 'tkhd')
  writeDuration(bytes, vt.durationAt, vt.wide, movieDuration)
  const mvhd = child(bytes, moov, 'mvhd') as Box
  const mv = timeFields(bytes, mvhd, 'mvhd')
  writeDuration(bytes, mv.durationAt, mv.wide, movieDuration)
  if (ai < 0) return bytes

  const atrak = traks[ai] as Box
  const atkhd = child(bytes, atrak, 'tkhd') as Box
  const at = timeFields(bytes, atkhd, 'tkhd')
  writeDuration(bytes, at.durationAt, at.wide, movieDuration)
  const audio = info.tracks[ai] as TrackInfo
  if (opts.primingSamples < 0 || opts.primingSamples > audio.duration) throw new Mp4Error('priming out of range')
  const edts = elstBox(movieDuration, opts.primingSamples)
  const existing = child(bytes, atrak, 'edts')
  // Replace an existing edts in place when it is the same size; otherwise insert after tkhd.
  if (existing && existing.size === edts.length) {
    bytes.set(edts, existing.start)
    return bytes
  }
  if (existing) throw new Mp4Error('unexpected edit list layout')
  const insertAt = atkhd.start + atkhd.size
  const top = boxes(bytes, 0, bytes.length)
  const moovIndex = top.findIndex((x) => x.type === 'moov')
  const after = top[moovIndex + 1]
  const useFree = after?.type === 'free' && after.size >= edts.length + 8
  const out = new Uint8Array(useFree ? bytes.length : bytes.length + edts.length)
  out.set(bytes.subarray(0, insertAt), 0)
  out.set(edts, insertAt)
  if (useFree && after) {
    // moov grows into the free box, which shrinks by the same amount: mdat stays where it was.
    out.set(bytes.subarray(insertAt, after.start), insertAt + edts.length)
    const freeAt = after.start + edts.length
    put32(out, freeAt, after.size - edts.length)
    out.set([102, 114, 101, 101], freeAt + 4)
    out.fill(0, freeAt + 8, after.start + after.size)
    out.set(bytes.subarray(after.start + after.size), after.start + after.size)
  } else {
    out.set(bytes.subarray(insertAt), insertAt + edts.length)
  }
  // Parent sizes (moov, trak) grow by the edit list.
  for (const box of [moov, atrak]) {
    if (box.header !== 8) throw new Mp4Error('64-bit box sizes are not supported here')
    put32(out, box.start, box.size + edts.length)
  }
  if (!useFree) {
    const newMoov = moovOf(out)
    for (const trak of boxes(out, newMoov.start + newMoov.header, newMoov.start + newMoov.size).filter((x) => x.type === 'trak')) {
      const stbl = path(out, trak, ['mdia', 'minf', 'stbl'])
      const stco = stbl ? child(out, stbl, 'stco') : null
      const co64 = stbl ? child(out, stbl, 'co64') : null
      if (stco) {
        const n = u32(out, stco.start + stco.header + 4)
        for (let i = 0; i < n; i++) {
          const o = stco.start + stco.header + 8 + 4 * i
          put32(out, o, u32(out, o) + edts.length)
        }
      }
      if (co64) {
        const n = u32(out, co64.start + co64.header + 4)
        for (let i = 0; i < n; i++) {
          const o = co64.start + co64.header + 8 + 8 * i
          put64(out, o, u64(out, o) + edts.length)
        }
      }
    }
  }
  return out
}
