import { describe, expect, it } from 'vitest'
import { audioOffset, blackSegments, containerMeasures, deliveryErrors, type DeliveryMeasures } from './deliveryQa'
import { boxes, fixBrowserMp4, Mp4Error, readMp4 } from './mp4'

// --- a tiny MP4 writer: just the boxes the reader and the fix touch -------------------------------------------
const be32 = (v: number) => [(v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255]
const be16 = (v: number) => [(v >>> 8) & 255, v & 255]
const ascii = (s: string) => [...s].map((c) => c.charCodeAt(0))
const box = (type: string, ...body: number[][]) => {
  const flat = body.flat()
  return [...be32(8 + flat.length), ...ascii(type), ...flat]
}
const full = (version = 0) => [version, 0, 0, 0]
const zeros = (n: number) => new Array<number>(n).fill(0)

function mvhd(timescale: number, duration: number) {
  return box('mvhd', full(), zeros(8), be32(timescale), be32(duration), zeros(80))
}
function tkhd(duration: number) {
  return box('tkhd', full(), zeros(8), be32(1), zeros(4), be32(duration), zeros(60))
}
function mdhd(timescale: number, duration: number) {
  return box('mdhd', full(), zeros(8), be32(timescale), be32(duration), zeros(4))
}
const hdlr = (kind: string) => box('hdlr', full(), zeros(4), ascii(kind), zeros(13))
function avc1(width: number, height: number) {
  // avcC: version 1, High profile (100), one tiny SPS and PPS, then chroma 4:2:0 (1) and 8-bit depths.
  const avcC = box('avcC', [1, 100, 0, 40, 0xff, 0xe1], be16(2), [0x67, 0x64], [1], be16(1), [0x68], [0xfc | 1, 0xf8, 0xf8, 0])
  return box('avc1', zeros(6), be16(1), zeros(16), be16(width), be16(height), zeros(50), avcC)
}
function mp4a() {
  // esds: ES_Descriptor(3) → DecoderConfigDescriptor(4) → DecoderSpecificInfo(5) = AAC LC (2), 48 kHz, stereo.
  const dsi = [5, 2, 0x11, 0x90]
  const dcd = [4, 13 + dsi.length, 0x40, 0x15, ...zeros(11), ...dsi]
  const es = [3, 3 + dcd.length, 0, 1, 0, ...dcd]
  return box('mp4a', zeros(6), be16(1), zeros(8), be16(2), be16(16), zeros(4), be32(48000 * 65536), box('esds', full(), es))
}
function stbl(entry: number[], stts: [number, number][], samples: number, offsets: number[]) {
  return box(
    'stbl',
    box('stsd', full(), be32(1), entry),
    box('stts', full(), be32(stts.length), stts.flatMap(([c, d]) => [...be32(c), ...be32(d)])),
    box('stsz', full(), be32(0), be32(samples)),
    box('stco', full(), be32(offsets.length), offsets.flatMap(be32)),
  )
}
function trak(kind: 'vide' | 'soun', movieDur: number, timescale: number, mediaDur: number, entry: number[], stts: [number, number][], samples: number, offsets: number[]) {
  return box('trak', tkhd(movieDur), box('mdia', mdhd(timescale, mediaDur), hdlr(kind), box('minf', stbl(entry, stts, samples, offsets))))
}

/** A browser-export-shaped file: video's last sample has duration 0, no edit list, optional free box after moov. */
function sample(freeBytes: number | null): Uint8Array {
  const build = (mdatAt: number) => {
    const moov = box(
      'moov',
      mvhd(57600, 1156301),
      trak('vide', 1150080, 57600, 1150080, avc1(1080, 1920), [[599, 1920], [1, 0]], 600, [mdatAt + 8, mdatAt + 108]),
      trak('soun', 1156301, 48000, 963584, mp4a(), [[941, 1024]], 941, [mdatAt + 58]),
    )
    const head = [...box('ftyp', ascii('isom'), zeros(4)), ...moov, ...(freeBytes === null ? [] : box('free', zeros(freeBytes)))]
    return head
  }
  const mdatAt = build(0).length
  return Uint8Array.from([...build(mdatAt), ...box('mdat', zeros(200))])
}

describe('readMp4', () => {
  it('reads tracks, codecs, timing and fast start', () => {
    const info = readMp4(sample(64))
    expect(info.topLevel).toEqual(['ftyp', 'moov', 'free', 'mdat'])
    expect(info.fastStart).toBe(true)
    expect(info.tracks.map((t) => [t.handler, t.codec, t.timescale, t.sampleCount])).toEqual([
      ['vide', 'avc1', 57600, 600],
      ['soun', 'mp4a', 48000, 941],
    ])
    expect(info.tracks[0]).toMatchObject({ width: 1080, height: 1920, avcProfile: 100, chromaFormat: 1, bitDepth: 8, stts: [[599, 1920], [1, 0]] })
    expect(info.tracks[1]).toMatchObject({ channels: 2, sampleRate: 48000, audioObjectType: 2, edits: [] })
  })

  it('refuses broken files', () => {
    const bad = sample(null)
    bad[3] = 4 // ftyp size below its header
    expect(() => readMp4(bad)).toThrow(Mp4Error)
    expect(() => readMp4(Uint8Array.from(box('free', zeros(4))))).toThrow(/no moov/)
  })
})

describe('fixBrowserMp4', () => {
  const offsets = (bytes: Uint8Array) => {
    const out: number[] = []
    const walk = (start: number, end: number) => {
      for (const b of boxes(bytes, start, end)) {
        if (['moov', 'trak', 'mdia', 'minf', 'stbl'].includes(b.type)) walk(b.start + 8, b.start + b.size)
        if (b.type === 'stco') {
          const v = new DataView(bytes.buffer, bytes.byteOffset)
          for (let i = 0; i < v.getUint32(b.start + 12); i++) out.push(v.getUint32(b.start + 16 + 4 * i))
        }
      }
    }
    walk(0, bytes.length)
    return out
  }

  it('sets the last frame duration, durations and the audio edit list, inside the free box', () => {
    const input = sample(64)
    const before = input.slice()
    const fixed = fixBrowserMp4(input, { fps: 30, frames: 600, primingSamples: 2112 })
    expect(input).toEqual(before)
    expect(fixed.length).toBe(input.length)
    const info = readMp4(fixed)
    expect(info.movieDuration).toBe(1152000)
    expect(info.tracks[0]).toMatchObject({ duration: 1152000, stts: [[599, 1920], [1, 1920]] })
    expect(info.tracks[1]?.edits).toEqual([[1152000, 2112]])
    expect(info.topLevel).toEqual(['ftyp', 'moov', 'free', 'mdat'])
    expect(offsets(fixed)).toEqual(offsets(input))
    // Re-running replaces the edit list instead of adding another.
    expect(readMp4(fixBrowserMp4(fixed, { fps: 30, frames: 600, primingSamples: 1024 })).tracks[1]?.edits).toEqual([[1152000, 1024]])
  })

  it('shifts mdat and every chunk offset when there is no room in a free box', () => {
    for (const free of [null, 20]) {
      const input = sample(free)
      const fixed = fixBrowserMp4(input, { fps: 30, frames: 600, primingSamples: 2112 })
      expect(fixed.length).toBe(input.length + 36)
      expect(offsets(fixed)).toEqual(offsets(input).map((o) => o + 36))
      expect(readMp4(fixed).tracks[1]?.edits).toEqual([[1152000, 2112]])
    }
  })

  it('refuses a frame count or timescale that does not match', () => {
    expect(() => fixBrowserMp4(sample(64), { fps: 30, frames: 599, primingSamples: 0 })).toThrow(/600 frames/)
    expect(() => fixBrowserMp4(sample(64), { fps: 29, frames: 600, primingSamples: 0 })).toThrow(/not a multiple/)
  })
})

describe('delivery QA', () => {
  const good = (): DeliveryMeasures => ({
    ...containerMeasures(readMp4(fixBrowserMp4(sample(64), { fps: 30, frames: 600, primingSamples: 2112 })), 1_400_000),
    loudnessLufs: -14,
    truePeakDbtp: -1.3,
    silenceStarts: [],
    blackSegments: 0,
    audioOffsetSamples: 0,
  })

  it('passes a fixed export and reads it like ffprobe', () => {
    const m = good()
    expect(m).toMatchObject({ durationSeconds: 20, fps: '30/1', videoCodec: 'h264', pixFmt: 'yuv420p', audioCodec: 'aac', audioSampleRate: 48000, audioChannels: 2, fastStart: true })
    expect(deliveryErrors(m, { frames: 600, fps: 30 })).toEqual([])
  })

  it('names every failed check like render.mjs', () => {
    const unfixed = { ...good(), ...containerMeasures(readMp4(sample(64)), 25_000_000) }
    expect(unfixed.fps).toBe('18000/599')
    expect(deliveryErrors({ ...unfixed, loudnessLufs: -17, truePeakDbtp: -0.2, silenceStarts: [4.5], blackSegments: 1, audioOffsetSamples: 2112 }, { frames: 600, fps: 30 })).toEqual([
      'fps 18000/599',
      'duration 20.075s',
      'size 25000000 > 24000000',
      'loudness -17.0 LUFS outside −14 ± 2',
      'true peak -0.2 dBTP above −1',
      '1 black segment(s)',
      'silence at 4.5s',
      'audio out of sync by 2112 samples',
    ])
    expect(deliveryErrors({ ...good(), loudnessLufs: -Infinity }, { frames: 600, fps: 30 })).toEqual(['loudness -Infinity LUFS outside −14 ± 2'])
  })

  it('counts black segments of 0.2 s or more', () => {
    expect(blackSegments([200, 3, 200, 3, 3, 3, 200, 2, 2])).toBe(2)
    expect(blackSegments([])).toBe(0)
  })

  it('finds the audio offset (AAC priming) and 0 once aligned', () => {
    let x = 3
    const ref = Float64Array.from({ length: 20000 }, (_, i) => {
      x = (x * 1103515245 + 12345) % 2147483648
      return i < 500 ? 0 : (x / 2147483648) * 2 - 1
    })
    const late = new Float64Array(ref.length + 2112)
    late.set(ref, 2112)
    expect(audioOffset([ref], [late], 4096, 8000)).toBe(2112)
    expect(audioOffset([ref, ref], [ref, ref], 4096, 8000)).toBe(0)
  })
})
