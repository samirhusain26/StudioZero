/** WAV (RIFF) reading and writing for planar float audio. Pure; no I/O. */

export interface PcmAudio {
  sampleRate: number
  /** One Float32Array per channel, values in [-1, 1]. */
  channels: Float32Array[]
}

export class WavError extends Error {}

const tag = (v: DataView, o: number) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3))

/** PCM 16/24/32-bit integer or 32-bit float, any channel count. */
export function readWav(buffer: ArrayBuffer): PcmAudio {
  const v = new DataView(buffer)
  if (buffer.byteLength < 12 || tag(v, 0) !== 'RIFF' || tag(v, 8) !== 'WAVE') throw new WavError('not a WAV file')
  let format = 0
  let channels = 0
  let sampleRate = 0
  let bits = 0
  let o = 12
  while (o + 8 <= buffer.byteLength) {
    const id = tag(v, o)
    const size = v.getUint32(o + 4, true)
    const body = o + 8
    if (id === 'fmt ') {
      format = v.getUint16(body, true)
      channels = v.getUint16(body + 2, true)
      sampleRate = v.getUint32(body + 4, true)
      bits = v.getUint16(body + 14, true)
      if (format === 0xfffe && size >= 26) format = v.getUint16(body + 24, true) // WAVE_FORMAT_EXTENSIBLE sub-format
    } else if (id === 'data') {
      if (!channels || !sampleRate) throw new WavError('data before fmt')
      const end = Math.min(body + size, buffer.byteLength)
      const bytes = bits / 8
      const frames = Math.floor((end - body) / (bytes * channels))
      const out = Array.from({ length: channels }, () => new Float32Array(frames))
      for (let i = 0; i < frames; i++) {
        for (let c = 0; c < channels; c++) {
          const at = body + (i * channels + c) * bytes
          let x: number
          if (format === 3 && bits === 32) x = v.getFloat32(at, true)
          else if (format === 1 && bits === 16) x = v.getInt16(at, true) / 32768
          else if (format === 1 && bits === 24) x = ((v.getUint8(at) | (v.getUint8(at + 1) << 8) | (v.getInt8(at + 2) << 16)) / 8388608)
          else if (format === 1 && bits === 32) x = v.getInt32(at, true) / 2147483648
          else throw new WavError(`unsupported WAV format ${format}/${bits}-bit`)
          ;(out[c] as Float32Array)[i] = x
        }
      }
      return { sampleRate, channels: out }
    }
    o = body + size + (size % 2)
  }
  throw new WavError('no data chunk')
}

/** 32-bit float WAV (no quantization before the AAC encoder). */
export function writeWavFloat(audio: PcmAudio): ArrayBuffer {
  const n = audio.channels.length
  const frames = audio.channels[0]?.length ?? 0
  const dataBytes = frames * n * 4
  const buffer = new ArrayBuffer(44 + dataBytes)
  const v = new DataView(buffer)
  const str = (o: number, s: string) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)))
  str(0, 'RIFF')
  v.setUint32(4, 36 + dataBytes, true)
  str(8, 'WAVE')
  str(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 3, true)
  v.setUint16(22, n, true)
  v.setUint32(24, audio.sampleRate, true)
  v.setUint32(28, audio.sampleRate * n * 4, true)
  v.setUint16(32, n * 4, true)
  v.setUint16(34, 32, true)
  str(36, 'data')
  v.setUint32(40, dataBytes, true)
  let o = 44
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < n; c++) {
      v.setFloat32(o, (audio.channels[c] as Float32Array)[i] ?? 0, true)
      o += 4
    }
  }
  return buffer
}
