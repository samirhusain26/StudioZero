/**
 * Audio measurements with the same definitions as the Mac QA (engines/motion/render/qa_media.py, master_audio.py):
 * integrated loudness per ITU-R BS.1770-4 (K-weighting and gating as pyloudnorm computes them), true peak by 4×
 * oversampling (BS.1770-4 Annex 2 interpolation filter), and silence gaps. Pure; no I/O.
 */

type Channels = readonly ArrayLike<number>[]

/** Biquad coefficients, normalized (a0 = 1). */
interface Biquad {
  b: [number, number, number]
  a: [number, number]
}

/** pyloudnorm's IIRfilter: high shelf (G 4 dB, Q 1/√2, 1500 Hz) then high pass (Q 0.5, 38 Hz). */
export function kWeighting(rate: number): [Biquad, Biquad] {
  const shelf = (() => {
    const A = 10 ** (4 / 40)
    const w0 = (2 * Math.PI * 1500) / rate
    const alpha = Math.sin(w0) / (2 * Math.SQRT1_2)
    const c = Math.cos(w0)
    const s = 2 * Math.sqrt(A) * alpha
    const a0 = A + 1 - (A - 1) * c + s
    return {
      b: [(A * (A + 1 + (A - 1) * c + s)) / a0, (-2 * A * (A - 1 + (A + 1) * c)) / a0, (A * (A + 1 + (A - 1) * c - s)) / a0],
      a: [(2 * (A - 1 - (A + 1) * c)) / a0, (A + 1 - (A - 1) * c - s) / a0],
    } as Biquad
  })()
  const highPass = (() => {
    const w0 = (2 * Math.PI * 38) / rate
    const alpha = Math.sin(w0) / (2 * 0.5)
    const c = Math.cos(w0)
    const a0 = 1 + alpha
    return { b: [(1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0], a: [(-2 * c) / a0, (1 - alpha) / a0] } as Biquad
  })()
  return [shelf, highPass]
}

function biquad(x: ArrayLike<number>, f: Biquad): Float64Array {
  const y = new Float64Array(x.length)
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0
  const [b0, b1, b2] = f.b
  const [a1, a2] = f.a
  for (let n = 0; n < x.length; n++) {
    const xn = x[n] ?? 0
    const yn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
    y[n] = yn
    x2 = x1
    x1 = xn
    y2 = y1
    y1 = yn
  }
  return y
}

/** Integrated loudness in LUFS (−Infinity for silence), gated as pyloudnorm.Meter.integrated_loudness. */
export function integratedLoudness(channels: Channels, rate: number): number {
  const [shelf, hp] = kWeighting(rate)
  const filtered = channels.map((ch) => biquad(biquad(ch, shelf), hp))
  const length = channels[0]?.length ?? 0
  const T = length / rate
  const Tg = 0.4
  const step = 0.25
  const blocks = Math.round((T - Tg) / (Tg * step)) + 1
  if (blocks < 1) return -Infinity
  // Channel weights: L, R, C = 1; Ls, Rs = 1.41 (stereo here).
  const G = [1, 1, 1, 1.41, 1.41]
  const z: number[][] = filtered.map(() => [])
  for (let j = 0; j < blocks; j++) {
    const l = Math.floor(Tg * (j * step) * rate)
    const u = Math.floor(Tg * (j * step + 1) * rate)
    filtered.forEach((ch, i) => {
      let sum = 0
      for (let n = l; n < Math.min(u, ch.length); n++) sum += (ch[n] as number) ** 2
      ;(z[i] as number[]).push(sum / (Tg * rate))
    })
  }
  const blockLoudness = (j: number) => -0.691 + 10 * Math.log10(z.reduce((s, zi, i) => s + (G[i] ?? 1) * (zi[j] as number), 0))
  const l = Array.from({ length: blocks }, (_, j) => blockLoudness(j))
  const gatedMean = (keep: (lj: number) => boolean) => {
    const idx = l.map((lj, j) => (keep(lj) ? j : -1)).filter((j) => j >= 0)
    return z.map((zi) => (idx.length ? idx.reduce((s, j) => s + (zi[j] as number), 0) / idx.length : 0))
  }
  const loud = (avg: number[]) => -0.691 + 10 * Math.log10(avg.reduce((s, v, i) => s + (G[i] ?? 1) * v, 0))
  const gammaA = -70
  const gammaR = loud(gatedMean((lj) => lj >= gammaA)) - 10
  return loud(gatedMean((lj) => lj > gammaR && lj > gammaA))
}

/** BS.1770-4 Annex 2: 48-tap FIR for 4× oversampling, as four 12-tap phases. */
const TP_PHASES: readonly (readonly number[])[] = [
  [0.001708984375, 0.010986328125, -0.0196533203125, 0.033203125, -0.0594482421875, 0.1373291015625, 0.97216796875, -0.102294921875, 0.0476074218750, -0.0266113281250, 0.0148925781250, -0.0083007812500],
  [-0.0291748046875, 0.029296875, -0.0517578125, 0.0891113281250, -0.166503906250, 0.4650878906250, 0.7797851562500, -0.2003173828125, 0.1015625, -0.0582275390625, 0.0330810546875, -0.0189208984375],
  [-0.0189208984375, 0.0330810546875, -0.0582275390625, 0.1015625, -0.2003173828125, 0.7797851562500, 0.4650878906250, -0.166503906250, 0.0891113281250, -0.0517578125, 0.029296875, -0.0291748046875],
  [-0.0083007812500, 0.0148925781250, -0.0266113281250, 0.0476074218750, -0.102294921875, 0.97216796875, 0.1373291015625, -0.0594482421875, 0.033203125, -0.0196533203125, 0.010986328125, 0.001708984375],
]

/** True peak in dBTP (max over channels of the 4× oversampled absolute value, never below the sample peak). */
export function truePeakDb(channels: Channels): number {
  let peak = 0
  for (const ch of channels) {
    for (let n = 0; n < ch.length; n++) {
      const s = Math.abs(ch[n] ?? 0)
      if (s > peak) peak = s
      for (const taps of TP_PHASES) {
        let acc = 0
        for (let k = 0; k < 12; k++) acc += (taps[k] as number) * (ch[n - k] ?? 0)
        const a = Math.abs(acc)
        if (a > peak) peak = a
      }
    }
  }
  return 20 * Math.log10(peak + 1e-12)
}

/**
 * Starts (seconds) of silence gaps: ≥ 1 s below −50 dBFS RMS in 50 ms windows of the mono mix, ignoring the last
 * 2 s (the closing fade). Same windows as qa_media.py.
 */
export function silenceStarts(channels: Channels, rate: number): number[] {
  const length = channels[0]?.length ?? 0
  const win = Math.floor(0.05 * rate)
  const duration = length / rate
  const out: number[] = []
  let run = 0
  for (let i = 0; (i + 1) * win <= length; i++) {
    let sum = 0
    for (let n = i * win; n < (i + 1) * win; n++) {
      let m = 0
      for (const ch of channels) m += ch[n] ?? 0
      m /= channels.length
      sum += m * m
    }
    const db = 20 * Math.log10(Math.sqrt(sum / win) + 1e-12)
    run = db < -50 ? run + 1 : 0
    if (run === 20 && i * 0.05 < duration - 2) out.push(Math.round((i - 19) * 0.05 * 100) / 100)
  }
  return out
}
