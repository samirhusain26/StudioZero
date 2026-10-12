import { describe, expect, it } from 'vitest'
import { integratedLoudness, silenceStarts, truePeakDb } from './loudness'
import { limit, master, minimumFilter, uniformFilter } from './master'
import { readWav, writeWavFloat } from './wav'

const RATE = 48000

function sine(seconds: number, dbfs: number, hz = 997, phase = 0): Float64Array {
  const a = 10 ** (dbfs / 20)
  return Float64Array.from({ length: Math.round(seconds * RATE) }, (_, n) => a * Math.sin((2 * Math.PI * hz * n) / RATE + phase))
}

function concat(...parts: Float64Array[]): Float64Array {
  const out = new Float64Array(parts.reduce((s, p) => s + p.length, 0))
  let o = 0
  for (const p of parts) {
    out.set(p, o)
    o += p.length
  }
  return out
}

/** Deterministic noise (xorshift), so the tests never depend on Math.random. */
function noise(seconds: number, amp: number, seed = 1): Float64Array {
  let x = seed
  return Float64Array.from({ length: Math.round(seconds * RATE) }, () => {
    x ^= x << 13
    x ^= x >>> 17
    x ^= x << 5
    return (((x >>> 0) / 4294967296) * 2 - 1) * amp
  })
}

describe('integrated loudness (BS.1770-4)', () => {
  it('reads the EBU Tech 3341 stereo sine cases', () => {
    for (const level of [-23, -33]) {
      const s = sine(20, level)
      expect(integratedLoudness([s, s], RATE)).toBeCloseTo(level, 1)
    }
  })

  it('gates silence out (absolute gate) and quiet passages out (relative gate)', () => {
    // Blocks straddling an edge count partly; the expected values are pyloudnorm's for the same signals.
    const loud = sine(10, -23)
    const silent = new Float64Array(10 * RATE)
    expect(integratedLoudness([concat(loud, silent), concat(loud, silent)], RATE)).toBeCloseTo(-23.107046, 5)
    const quiet = sine(10, -50)
    expect(integratedLoudness([concat(quiet, loud, quiet), concat(quiet, loud, quiet)], RATE)).toBeCloseTo(-23.169519, 5)
    expect(integratedLoudness([silent, silent], RATE)).toBe(-Infinity)
  })
})

describe('true peak', () => {
  it('finds the inter-sample peak of a fs/4 sine sampled at 45°', () => {
    const s = sine(1, 0, RATE / 4, Math.PI / 4)
    expect(Math.max(...s.map(Math.abs))).toBeCloseTo(Math.SQRT1_2, 6)
    expect(truePeakDb([s])).toBeGreaterThan(-0.3)
    expect(truePeakDb([s])).toBeLessThan(0.3)
  })

  it('is the sample peak for a slow sine', () => {
    expect(truePeakDb([sine(1, -6, 100)])).toBeCloseTo(-6, 1)
  })
})

describe('silence gaps', () => {
  it('reports gaps of 1 s or more below −50 dBFS, except in the last 2 s', () => {
    const tone = sine(3, -20)
    const gap = new Float64Array(Math.round(1.5 * RATE))
    const short = new Float64Array(Math.round(0.6 * RATE))
    const mix = concat(tone, gap, tone, short, tone, new Float64Array(Math.round(1.8 * RATE)))
    expect(silenceStarts([mix, mix], RATE)).toEqual([3])
  })
})

describe('mastering (master_audio.py port)', () => {
  const brute = (x: Float64Array, size: number, f: (w: number[]) => number, before: number) => {
    const n = x.length
    const r = (i: number): number => {
      let k = i
      while (k < 0 || k >= n) k = k < 0 ? -k - 1 : 2 * n - k - 1
      return x[k] as number
    }
    return Float64Array.from({ length: n }, (_, i) => f(Array.from({ length: size }, (_, k) => r(i - before + k))))
  }

  it('filters like scipy.ndimage (reflect boundary, centred windows)', () => {
    const x = Float64Array.from([5, 3, 8, 1, 9, 2, 7, 4, 6, 0, 3])
    expect([...minimumFilter(x, 5)]).toEqual([...brute(x, 5, (w) => Math.min(...w), 2)])
    expect([...minimumFilter(x, 31)]).toEqual([...brute(x, 31, (w) => Math.min(...w), 15)])
    const mean = (w: number[]) => w.reduce((s, v) => s + v, 0) / w.length
    for (const size of [4, 5, 6])
      [...uniformFilter(x, size)].forEach((v, i) => expect(v).toBeCloseTo(brute(x, size, mean, Math.floor(size / 2))[i] as number, 12))
  })

  it('limits peaks to the ceiling and keeps quiet audio untouched', () => {
    const quiet = sine(0.5, -20)
    const hot = sine(0.5, 3)
    const [out] = limit([concat(quiet, hot)], 10 ** (-1.5 / 20), RATE)
    const peak = Math.max(...(out as Float64Array).subarray(quiet.length).map(Math.abs))
    expect(peak).toBeLessThanOrEqual(10 ** (-1.5 / 20) + 1e-9)
    expect((out as Float64Array)[1000]).toBeCloseTo(quiet[1000] as number, 12)
  })

  it('reaches −14 LUFS with true peak ≤ −1 dBTP, sample-aligned', () => {
    const l = concat(noise(4, 0.05, 7), sine(2, -3, 440), noise(4, 0.02, 9))
    const r = concat(noise(4, 0.05, 11), sine(2, -3, 660), noise(4, 0.02, 13))
    const result = master({ sampleRate: RATE, channels: [Float32Array.from(l), Float32Array.from(r)] })
    expect(result.lufs).toBeCloseTo(-14, 1)
    expect(result.truePeakDbtp).toBeLessThanOrEqual(-1)
    expect(result.audio.channels[0]?.length).toBe(l.length)
    expect(integratedLoudness(result.audio.channels, RATE)).toBeCloseTo(-14, 1)
  })

  it('refuses a silent mix', () => {
    const silent = new Float32Array(RATE)
    expect(() => master({ sampleRate: RATE, channels: [silent, silent] })).toThrow(/silent/)
  })
})

describe('WAV', () => {
  it('round-trips float WAV and reads 16- and 24-bit PCM', () => {
    const ch = [Float32Array.from([0, 0.5, -0.25, 1]), Float32Array.from([-1, 0.125, 0, 0.75])]
    const back = readWav(writeWavFloat({ sampleRate: RATE, channels: ch }))
    expect(back.sampleRate).toBe(RATE)
    expect(back.channels.map((c) => [...c])).toEqual(ch.map((c) => [...c]))

    const pcm = (bits: 16 | 24, samples: number[]) => {
      const bytes = bits / 8
      const buf = new ArrayBuffer(44 + samples.length * bytes)
      const v = new DataView(buf)
      const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
      str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * bytes, true); str(8, 'WAVE'); str(12, 'fmt ')
      v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, RATE, true)
      v.setUint32(28, RATE * bytes, true); v.setUint16(32, bytes, true); v.setUint16(34, bits, true)
      str(36, 'data'); v.setUint32(40, samples.length * bytes, true)
      samples.forEach((s, i) => {
        if (bits === 16) v.setInt16(44 + i * 2, s, true)
        else { v.setUint8(44 + i * 3, s & 255); v.setUint8(45 + i * 3, (s >> 8) & 255); v.setInt8(46 + i * 3, s >> 16) }
      })
      return buf
    }
    expect([...readWav(pcm(16, [16384, -32768])).channels[0] ?? []]).toEqual([0.5, -1])
    expect([...readWav(pcm(24, [4194304, -8388608])).channels[0] ?? []]).toEqual([0.5, -1])
    expect(() => readWav(new ArrayBuffer(8))).toThrow(/not a WAV/)
  })
})
