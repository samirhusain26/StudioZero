import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError } from '../api/client'
import { stopReason, useAutoRefresh } from './useAutoRefresh'

let hidden = false

beforeEach(() => {
  hidden = false
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => (hidden ? 'hidden' : 'visible'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

describe('useAutoRefresh', () => {
  it('polls every 30 s while visible and stops when the tab is hidden', async () => {
    const load = vi.fn().mockResolvedValue({ ok: 1 })
    const { result } = renderHook(() => useAutoRefresh(load))
    await flush()
    expect(load).toHaveBeenCalledTimes(1)
    expect(result.current.updatedAt).not.toBeNull()
    await advance(30_000)
    expect(load).toHaveBeenCalledTimes(2)
    hidden = true
    document.dispatchEvent(new Event('visibilitychange'))
    await advance(120_000)
    expect(load).toHaveBeenCalledTimes(2)
    hidden = false
    document.dispatchEvent(new Event('visibilitychange'))
    await flush()
    expect(load).toHaveBeenCalledTimes(3) // stale on return: refresh at once
  })

  it('never overlaps requests', async () => {
    let resolve: (value: number) => void = () => {}
    const load = vi.fn(() => new Promise<number>((r) => (resolve = r)))
    const { result } = renderHook(() => useAutoRefresh(load))
    await advance(90_000)
    act(() => result.current.reload())
    expect(load).toHaveBeenCalledTimes(1)
    await act(async () => resolve(1))
    expect(result.current.data).toBe(1)
    await advance(29_000)
    expect(load).toHaveBeenCalledTimes(1)
    await advance(1_000)
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('pauses and resumes on request', async () => {
    const load = vi.fn().mockResolvedValue(1)
    const { result } = renderHook(() => useAutoRefresh(load))
    await flush()
    act(() => result.current.setAuto(false))
    await advance(120_000)
    expect(load).toHaveBeenCalledTimes(1)
    act(() => result.current.setAuto(true))
    await flush()
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('stops polling on 429 and 401 until a manual reload', async () => {
    const load = vi.fn().mockRejectedValueOnce(new ApiRequestError(429, 'Too many attempts.', null, 120)).mockResolvedValue(1)
    const { result } = renderHook(() => useAutoRefresh(load))
    await flush()
    expect(result.current.stopped).toMatch(/too many attempts.*2 minutes/i)
    await advance(300_000)
    expect(load).toHaveBeenCalledTimes(1)
    act(() => result.current.reload())
    await flush()
    expect(result.current.stopped).toBeNull()
    expect(result.current.data).toBe(1)
    expect(stopReason(new ApiRequestError(401, 'x', null))).toMatch(/passcode/)
    expect(stopReason(new ApiRequestError(500, 'x', null))).toBeNull()
  })
})
