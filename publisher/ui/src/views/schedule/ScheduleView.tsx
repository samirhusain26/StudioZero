import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ChannelSummary, DraftResponse, Platform, ScheduleInputs, ScheduleResponse } from '../../api/types'
import { PLATFORMS } from '../../api/types'
import { ActionBar } from '../../components/ActionBar'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { useJourney } from '../../hooks/useJourney'
import { approvalResultText } from '../../lib/approvalResult'
import { platformName, shortHash } from '../../lib/format'
import {
  buildScheduleInputs,
  presetForm,
  presetStartDate,
  RECOMMENDED_DAYS,
  RECOMMENDED_TIMES,
  SUGGESTED_TIMEZONE,
  withEdit,
  type ScheduleForm,
} from '../../lib/scheduleForm'
import { formatLocal, localDateKey } from '../../lib/time'
import { ApprovalPanel } from './ApprovalPanel'
import { ContentCalendar } from './ContentCalendar'
import { DraftPreview } from './DraftPreview'
import { GeneratorForm } from './GeneratorForm'
import { QueueList } from './QueueList'

const POLL_MS = 4000
const POLL_LIMIT = 150

function blockedSet(channels: readonly ChannelSummary[]): Set<Platform> {
  return new Set(channels.filter((c) => c.blockedReason).map((c) => c.platform))
}

function today(): string {
  return localDateKey(new Date().toISOString(), SUGGESTED_TIMEZONE)
}

/** Schedule: the approved schedule, then a new draft (preset first, Customize behind one disclosure), preview and approval. */
export function ScheduleView({ queue = false }: { queue?: boolean }) {
  const schedule = useApi(api.schedule)
  const library = useApi(api.library)
  const loop = useJourney()
  const [draft, setDraft] = useState<DraftResponse | null>(null)
  const [previousSha, setPreviousSha] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [approveError, setApproveError] = useState<unknown>(null)
  const [polling, setPolling] = useState(false)
  const setScheduleData = schedule.setData
  const reloadLoop = loop.reload

  const showDraft = (next: DraftResponse) => {
    setPreviousSha(draft && draft.sha256 !== next.sha256 ? draft.sha256 : null)
    setDraft(next)
    setApproveError(null)
  }

  const runDraft = async (make: () => Promise<DraftResponse>) => {
    setBusy(true)
    setError(null)
    try {
      showDraft(await make())
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const generate = (inputs: ScheduleInputs) => {
    setPreviousSha(null)
    void runDraft(() => api.createDraft(inputs))
  }

  const fromQueue = (make: () => Promise<DraftResponse>) => {
    // A cancel or edit makes a new draft: show it on the Schedule screen with its approval panel.
    window.location.hash = '/schedule'
    void runDraft(make)
  }

  const approve = async (confirmation: string) => {
    if (!draft) return
    setBusy(true)
    setApproveError(null)
    try {
      await api.approveDraft(draft.sha256, confirmation)
      setScheduleData(await api.schedule())
      setPolling(true)
    } catch (e) {
      setApproveError(e)
    } finally {
      setBusy(false)
    }
  }

  // Poll while an approval request is pending, until a terminal result arrives.
  useEffect(() => {
    if (!polling || !draft) return
    let count = 0
    const timer = setInterval(() => {
      count++
      api.schedule().then(
        (data) => {
          setScheduleData(data)
          const result = data.lastResult?.draftSha256 === draft.sha256 ? data.lastResult : null
          const terminal = result !== null && result.status !== 'manifest-ready'
          if ((terminal && !data.pendingRequest) || count >= POLL_LIMIT) {
            setPolling(false)
            reloadLoop()
          }
        },
        () => {
          if (count >= POLL_LIMIT) setPolling(false)
        },
      )
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [polling, draft, setScheduleData, reloadLoop])

  const data = schedule.data
  const zone = data?.displayTimezone ?? 'UTC'
  const lastResult = data?.lastResult && draft && data.lastResult.draftSha256 === draft.sha256 ? data.lastResult : null

  if (queue) {
    return (
      <div className="stack-lg">
        <p className="review-nav">
          <a href="#/schedule">← Schedule</a>
        </p>
        <ErrorNotice error={schedule.error} title="Schedule unavailable" />
        {data ? (
          <QueueList
            schedule={data}
            busy={busy}
            onCancel={(keys) => fromQueue(() => api.cancelJobs({ keys }))}
            onEdit={(key, text) => fromQueue(() => api.editJob({ key, text }))}
          />
        ) : schedule.loading ? (
          <Loading />
        ) : null}
      </div>
    )
  }

  return (
    <div className="stack-lg">
      <ScreenHelp id="schedule" />
      <ErrorNotice error={schedule.error} title="Schedule unavailable" />
      {data ? <ApprovedSchedule schedule={data} /> : schedule.loading ? <Loading /> : null}
      {data ? <ContentCalendar schedule={data} episodes={library.data?.episodes ?? null} /> : null}
      <NewDraft channels={data?.channels ?? []} busy={busy} onGenerate={generate} />
      <div aria-live="polite">{busy && !draft ? <Loading label="Working…" /> : null}</div>
      <ErrorNotice error={error} title="Draft not created" />
      {draft ? (
        <div className="draft-layout">
          <div className="phone-only">
            <ActionBar label="Draft actions">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  const panel = document.querySelector<HTMLElement>('[data-testid="approval-panel"]')
                  panel?.scrollIntoView({ block: 'start' })
                  panel?.querySelector<HTMLInputElement>('input')?.focus({ preventScroll: true })
                }}
              >
                Go to approval ↓
              </button>
            </ActionBar>
          </div>
          <div className="draft-main">
            <DraftPreview
              draft={draft}
              previousSha={previousSha}
              busy={busy}
              onEdit={(key, text) => void runDraft(() => api.createDraft(withEdit(draft.draft.inputs, key, { text })))}
              onRemove={(key) => void runDraft(() => api.createDraft(withEdit(draft.draft.inputs, key, { remove: true })))}
              onRegenerate={() => void runDraft(() => api.createDraft(draft.draft.inputs))}
            />
          </div>
          <div className="draft-side">
            <ApprovalPanel
              key={draft.sha256}
              draft={draft}
              pendingRequest={data?.pendingRequest ?? null}
              lastResult={lastResult}
              zone={zone}
              busy={busy}
              error={approveError}
              onApprove={approve}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}

/** The approved schedule in one card: span, hash, when, the next posts and the way into the queue. */
export function ApprovedSchedule({ schedule, now = new Date() }: { schedule: ScheduleResponse; now?: Date }) {
  const zone = schedule.displayTimezone
  const manifest = schedule.manifest
  const posts = schedule.jobs.filter((j) => j.kind === 'post')
  const days = [...new Set(posts.map((j) => localDateKey(j.slotUtc, zone)))].sort()
  const upcoming = posts.filter((j) => !j.dispatched && Date.parse(j.slotUtc) > now.getTime()).sort((a, b) => a.slotUtc.localeCompare(b.slotUtc)).slice(0, 3)
  const result = schedule.lastResult ? approvalResultText(schedule.lastResult) : null
  return (
    <section className="card stack" aria-labelledby="approved-h" data-testid="approved-schedule">
      <h2 id="approved-h">Approved schedule</h2>
      {manifest ? (
        <>
          <p>
            {days.length} day{days.length === 1 ? '' : 's'}
            {days.length ? ` · ${days[0]} → ${days[days.length - 1]}` : ''} · hash <code>{shortHash(manifest.sha256)}</code> · approved{' '}
            <Time iso={manifest.approvedAt} zone={zone} />
            {manifest.bound ? null : <span className="block muted">Waiting for the bind step.</span>}
          </p>
          <p className="muted">
            {upcoming.length
              ? `Next: ${upcoming.map((j) => `${platformName(j.platform)} ${formatLocal(j.slotUtc, zone)}`).join(' · ')}`
              : 'No more posts scheduled. Generate the next draft below.'}
          </p>
          <div className="actions">
            <a className="btn" href="#/schedule/queue">
              View queue ({schedule.jobs.length})
            </a>
          </div>
        </>
      ) : (
        <p>
          No approved schedule yet. Generate a draft below from the approved episodes; nothing approved yet?{' '}
          <a href="#/library">Approve episodes first →</a>
        </p>
      )}
      {schedule.pendingRequest ? (
        <p>
          <StatusBadge tone="info" label="Approval running" /> Draft <code>{shortHash(schedule.pendingRequest.draftSha256)}</code>, requested{' '}
          <Time iso={schedule.pendingRequest.requestedAt} zone={zone} />
        </p>
      ) : null}
      {result ? (
        <p>
          Last approval: <StatusBadge tone={result.tone} label={result.label} /> {result.detail}
        </p>
      ) : null}
    </section>
  )
}

/**
 * New draft, preset first. The recommended plan is shown as a proposal; only the start date and timezone are
 * visible fields. Nothing becomes form state until Generate draft or Customize is tapped.
 */
export function NewDraft({ channels, busy, onGenerate }: { channels: ChannelSummary[]; busy: boolean; onGenerate: (inputs: ScheduleInputs) => void }) {
  const [day] = useState(today)
  const [startDate, setStartDate] = useState(() => presetStartDate(day))
  const [timezone, setTimezone] = useState(SUGGESTED_TIMEZONE)
  const [changingZone, setChangingZone] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [customized, setCustomized] = useState<ScheduleForm | null>(null)
  const blocked = blockedSet(channels)
  const included = PLATFORMS.filter((p) => !blocked.has(p)).sort((a, b) => RECOMMENDED_TIMES[a].localeCompare(RECOMMENDED_TIMES[b]))
  const preset = () => presetForm(day, blocked, { startDate, timezone })

  const generate = () => {
    const built = buildScheduleInputs(preset())
    if (!built.ok) {
      setErrors(built.errors)
      return
    }
    setErrors([])
    onGenerate(built.inputs)
  }

  return (
    <section className="card stack" aria-labelledby="new-draft-h" data-testid="new-draft">
      <h2 id="new-draft-h">New draft</h2>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="p-start">Start date</label>
          <input id="p-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} disabled={Boolean(customized)} />
        </div>
        <div className="field">
          <span className="label" id="p-zone-label">
            Timezone
          </span>
          {changingZone ? (
            <input
              id="p-zone"
              aria-labelledby="p-zone-label"
              type="text"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              disabled={Boolean(customized)}
            />
          ) : (
            <p className="inline">
              <span aria-describedby="p-zone-label">{timezone}</span>
              <button type="button" className="btn btn-quiet" onClick={() => setChangingZone(true)} disabled={Boolean(customized)}>
                Change
              </button>
            </p>
          )}
        </div>
      </div>
      <p>
        Recommended plan: one post per platform per day for {RECOMMENDED_DAYS} days.
        <span className="block muted" data-testid="preset-times">
          {included.map((p) => `${platformName(p)} ${RECOMMENDED_TIMES[p]}`).join(' · ')}
        </span>
      </p>
      {blocked.size ? (
        <p className="muted">
          Blocked today:{' '}
          {channels
            .filter((c) => c.blockedReason)
            .map((c) => `${platformName(c.platform)} (${c.blockedReason})`)
            .join(' · ')}
        </p>
      ) : null}
      <details
        className="disclosure"
        onToggle={(e) => {
          // Opening Customize turns the proposal into form state, already filled with the preset values.
          if (e.currentTarget.open && !customized) setCustomized(preset())
        }}
      >
        <summary>Customize</summary>
        {customized ? <GeneratorForm channels={channels} busy={busy} onGenerate={onGenerate} initial={customized} /> : null}
      </details>
      {errors.length ? (
        <div className="notice notice-error" role="alert">
          <ul>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {customized ? (
        <p className="hint">Customized: generate from the form above.</p>
      ) : (
        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={generate} disabled={busy}>
            {busy ? 'Generating…' : 'Generate draft'}
          </button>
        </div>
      )}
    </section>
  )
}
