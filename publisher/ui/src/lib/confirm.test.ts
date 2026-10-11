import { describe, expect, it } from 'vitest'
import { approvalGate, confirmationPhrase } from './confirm'
import { SHA } from '../test/fixtures'

describe('approval gating', () => {
  const base = { blockingProblems: [] as string[], pending: false }

  it('builds APPROVE <first 8 hex>', () => {
    expect(confirmationPhrase(SHA)).toBe('APPROVE ab12cd34')
  })

  it('is enabled with nothing blocking and nothing pending; nothing is typed', () => {
    expect(approvalGate(base)).toEqual({ allowed: true, reason: null })
  })

  it('stays disabled with blocking problems or a pending request', () => {
    expect(approvalGate({ ...base, blockingProblems: ['Library changed'] }).allowed).toBe(false)
    expect(approvalGate({ ...base, pending: true }).allowed).toBe(false)
  })
})
