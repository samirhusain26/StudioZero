import type {
  AuthStatus,
  DashboardResponse,
  DraftJob,
  DraftResponse,
  Platform,
  PostingTestStatus,
  RecurringPlatformStatus,
  UpdateCheck,
  UpdateInfo,
  UpdateStatus,
} from '../api/types'
import { PLATFORMS } from '../api/types'

function perPlatform<T>(make: (p: Platform) => T): Record<Platform, T> {
  const out = {} as Record<Platform, T>
  for (const p of PLATFORMS) out[p] = make(p)
  return out
}

export const SHA = 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12'

export function dashboardFixture(): DashboardResponse {
  const posting = perPlatform<PostingTestStatus>((p) => ({
    state: p === 'instagram' ? 'yes' : 'no',
    label: p === 'instagram' ? 'Passed' : 'Not run',
    passedAt: p === 'instagram' ? '2026-10-05T14:00:00Z' : null,
    permalink: null,
    detail: null,
  }))
  const auth = perPlatform<AuthStatus>((p) => ({
    state: p === 'threads' ? 'yes' : 'unknown',
    label: p === 'threads' ? 'Authenticated' : 'Unknown',
    checkedAt: null,
    expiresAt: null,
    renewalFailed: false,
    detail: null,
  }))
  const recurring = perPlatform<RecurringPlatformStatus>(() => ({
    state: 'no',
    label: 'Disabled',
    channelEnabled: false,
    route: 'disabled',
    identityVerified: false,
    publishingVerified: false,
    detail: null,
  }))
  return {
    generatedAt: '2026-10-06T22:00:00Z',
    displayTimezone: 'America/New_York',
    paused: true,
    statuses: {
      postingTestPassed: { platforms: posting },
      currentlyAuthenticated: { platforms: auth },
      recurringEnabled: {
        state: 'no',
        label: 'Not enabled',
        configPaused: true,
        pausedSentinel: true,
        publisherTimerEnabled: false,
        publisherTimerActive: false,
        platforms: recurring,
      },
    },
    timers: [
      {
        unit: 'scalar-social.timer',
        role: 'publisher',
        label: 'Publisher',
        enabled: false,
        active: false,
        lastRunAt: null,
        lastResult: 'never',
        lastResultDetail: null,
        nextRunAt: null,
      },
    ],
    freshness: {
      healthJson: { updatedAt: '2026-10-06T21:55:00Z', ageSeconds: 300, maxAgeSeconds: 7200, fresh: true, label: 'Updated 5 min ago', ok: true },
      monitor: { updatedAt: null, ageSeconds: null, maxAgeSeconds: 7200, fresh: false, label: 'Missing', ok: null },
    },
    budgets: {
      pages: { used: 7, limit: 120, remaining: 113, window: 'last 31 days', label: '7 of 120 deployments used', low: false },
      buffer: { used: 3, limit: 200, remaining: 197, window: 'last 24 hours', label: '3 of 200 calls used', low: false },
    },
    storage: { freeBytes: 20e9, totalBytes: 32e9, reserveBytes: 2e9, low: false, label: '20 GB free' },
    issues: [
      {
        id: 'monitor-stale',
        severity: 'warning',
        category: 'monitor-stale',
        title: 'Monitor has not reported',
        detail: 'No monitor result was found.',
        nextAction: 'Check scalar-social-monitor.timer.',
        platform: null,
        jobId: null,
        at: null,
      },
    ],
    approval: { manifestSha256: null, approvedAt: null, bound: false, scope: [], pendingRequest: null, lastResult: null },
    standing: {
      lastBatch: { batchId: '2026-10-b01', importedAt: '2026-10-05T18:00:00Z', episodeCount: 12, awaitingFiles: 0 },
      awaitingReview: 3,
      nextPosts: [],
      openFeedback: 2,
      nextBatchId: '2026-10-b02',
      postedLast7Days: 0,
      lastBriefAt: null,
      lastRetroAt: null,
      contentThrough: null,
      nextBatchBy: null,
    },
    uncertainJobs: [
      {
        jobId: 'job123456789',
        platform: 'x',
        accountId: 'acct-x',
        slotUtc: '2026-10-05T12:00:00Z',
        episode: 'ep03',
        status: 'uncertain',
        dispatchedAt: '2026-10-05T12:00:05Z',
        error: {
          category: 'uncertain_response',
          title: 'Platform response unclear',
          detail: 'The request may have succeeded.',
          nextAction: 'Check the profile.',
        },
        reconciliation: {
          state: 'uncertain',
          label: 'Waiting for the platform to confirm',
          lastCheckAt: '2026-10-06T20:00:00Z',
          nextCheckAt: '2026-10-06T21:00:00Z',
          ownerActions: ['Check the X profile for this post.', 'If it is there, mark it resolved with evidence (sudo).'],
        },
      },
    ],
  }
}

export const RUNNING = '1111111111111111111111111111111111111111'
export const ORIGIN = '2222222222222222222222222222222222222222'

export function updateInfo(overrides: { status?: Partial<UpdateStatus>; check?: Partial<UpdateCheck> | null } & Partial<Omit<UpdateInfo, 'status'>> = {}): UpdateInfo {
  const { status, check, ...rest } = overrides
  const baseCheck: UpdateCheck = {
    checkedAt: '2026-10-20T11:55:00Z',
    fetchOk: true,
    head: RUNNING,
    origin: ORIGIN,
    behind: 2,
    ahead: 0,
    dirty: false,
    diverged: false,
    branchOk: true,
    originOk: true,
    originUrl: 'git@github.com-scalar:samirhusain26/scalargame-marketing.git',
    incoming: [
      { sha: ORIGIN, subject: 'ui: add the guide', date: '2026-10-20T10:00:00Z' },
      { sha: '3333333333333333333333333333333333333333', subject: 'updater: staged checks', date: '2026-10-19T10:00:00Z' },
    ],
    changes: { units: false, piPackage: false, contract: false, ui: true, files: ['publisher/app/static/index.html'] },
    error: null,
  }
  return {
    runningCommit: RUNNING,
    installKind: 'git',
    repoHead: RUNNING,
    restartNeeded: false,
    unitsChanged: false,
    piPackageChanged: false,
    applyUnitsCommand: null,
    unitsApply: null,
    ...rest,
    status: {
      phase: 'checked',
      requestId: 'req-1',
      startedAt: '2026-10-20T11:54:00Z',
      updatedAt: '2026-10-20T11:55:00Z',
      fromCommit: null,
      toCommit: null,
      error: null,
      log: [],
      check: check === null ? null : { ...baseCheck, ...check },
      ...status,
    },
  }
}

export function draftJob(overrides: Partial<DraftJob> = {}): DraftJob {
  return {
    key: 'instagram|2026-10-12T13:00:00+00:00|scalar:BOL:clues',
    platform: 'instagram',
    accountId: 'acct-ig',
    slotUtc: '2026-10-12T13:00:00+00:00',
    slotLocal: '2026-10-12T09:00:00-04:00',
    zone: 'EDT',
    kind: 'post',
    episodeKey: 'scalar:BOL:clues',
    parentKey: null,
    episodeId: 'scalar-clues-001',
    revision: 1,
    batchId: '2026-10-pilots',
    questionId: 'scalar:BOL:clues',
    game: 'scalar',
    videoSha256: SHA,
    coverSha256: SHA,
    text: 'Three clues, one country. A) Bolivia B) Paraguay C) Austria',
    youtube: null,
    thread: null,
    poll: null,
    link: null,
    carried: false,
    warnings: [],
    ...overrides,
  }
}

export function draftResponse(overrides: Partial<DraftResponse> = {}): DraftResponse {
  const post = draftJob()
  const comment = draftJob({
    key: 'instagram|2026-10-12T13:02:00+00:00|scalar:BOL:clues#comment',
    slotUtc: '2026-10-12T13:02:00+00:00',
    slotLocal: '2026-10-12T09:02:00-04:00',
    kind: 'comment',
    episodeKey: 'scalar:BOL:clues#comment',
    parentKey: post.key,
    videoSha256: null,
    coverSha256: null,
    text: 'A) Bolivia  B) Paraguay  C) Austria — comment your letter',
  })
  return {
    sha256: SHA,
    status: 'draft',
    createdAt: '2026-10-06T22:00:00Z',
    blockingProblems: [],
    confirmationPhrase: `APPROVE ${SHA.slice(0, 8)}`,
    coverUrls: {},
    draft: {
      version: 1,
      inputs: {
        timezone: 'America/New_York',
        startDate: '2026-10-12',
        endDate: '2026-10-25',
        platforms: { instagram: { include: true, weekdays: [0], times: ['09:00'], maxPerDay: 1 } },
        minGapHours: { instagram: 20 },
        staggerMinutes: 0,
        ordering: 'game-round-robin',
        companions: { firstComment: true, answerReply: false },
        edits: {},
      },
      baseManifestSha256: null,
      libraryHash: SHA,
      historyHash: SHA,
      jobs: [comment, post],
      unfilled: [{ platform: 'instagram', slotLocal: '2026-10-19T09:00:00-04:00', slotUtc: '2026-10-19T13:00:00+00:00', reason: 'No approved video left' }],
      excluded: [{ platform: 'tiktok', reason: 'Blocked: Buffer reconnect pending' }],
      warnings: [],
      summary: { requested: 2, filled: 1, companions: 1 },
    },
    ...overrides,
  }
}
