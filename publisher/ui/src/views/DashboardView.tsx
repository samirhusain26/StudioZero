import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { DashboardResponse, UpdateInfo } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Loading } from '../components/Loading'
import { RefreshLine } from '../components/RefreshLine'
import { ScreenHelp } from '../components/ScreenHelp'
import { StatusBadge } from '../components/StatusBadge'
import { Time } from '../components/Time'
import { useAutoRefresh } from '../hooks/useAutoRefresh'
import { useJourney } from '../hooks/useJourney'
import { attentionItems, platformRows, type AttentionItem, type PlatformRow } from '../lib/home'
import { journey as buildJourney, type Journey, type StepState } from '../lib/journey'
import type { Tone } from '../lib/labels'
import { deviceTimeZone } from '../lib/time'

/** Home: the loop first, then what needs a look, then one row per platform (docs/PI_UI_REDESIGN_PLAN.md §4.1). */
export function DashboardView({ onNavigate }: { onNavigate: (path: string) => void }) {
  const { data, error, loading, reload, updatedAt, auto, setAuto, stopped } = useAutoRefresh((signal) => api.dashboard(signal))
  const loop = useJourney()
  const { accept } = loop
  // Home polls; the shell's copy follows it so the step line and the loop card never disagree.
  useEffect(() => {
    if (data) accept(data)
  }, [data, accept])
  const j = loop.journey ?? (data ? buildJourney({ dashboard: data, update: loop.update, make: null, now: new Date() }) : null)
  return (
    <>
      <RefreshLine
        updatedAt={updatedAt}
        zone={data?.displayTimezone ?? deviceTimeZone()}
        auto={auto}
        onToggle={setAuto}
        onRefresh={reload}
        loading={loading}
        stopped={stopped}
      />
      <ErrorNotice error={error} title="Home unavailable" />
      {data && j ? <HomeContent data={data} journey={j} update={loop.update} onNavigate={onNavigate} /> : loading ? <Loading /> : null}
    </>
  )
}

export function HomeContent({
  data,
  journey,
  update = null,
  onNavigate,
  now = new Date(),
}: {
  data: DashboardResponse
  journey: Journey
  update?: UpdateInfo | null
  onNavigate: (path: string) => void
  now?: Date
}) {
  const attention = attentionItems(data, update, journey.focus, now)
  return (
    <div className="stack-lg">
      <LoopCard journey={journey} onNavigate={onNavigate} />
      <ScreenHelp id="home" />
      {attention.length ? <AttentionList items={attention} onNavigate={onNavigate} /> : null}
      <PlatformsCard data={data} rows={platformRows(data, now)} />
    </div>
  )
}

const STATE_WORDS: Record<StepState, string> = { done: 'done', current: 'your next step', blocked: 'blocked', todo: 'not yet' }
const STATE_MARKS: Record<StepState, string> = { done: '✓', current: '●', blocked: '!', todo: '' }

function Go({ to, onNavigate, className, children }: { to: string; onNavigate: (path: string) => void; className?: string; children: string }) {
  return (
    <a
      className={className}
      href={`#/${to}`}
      onClick={(e) => {
        e.preventDefault()
        onNavigate(to)
      }}
    >
      {children}
    </a>
  )
}

export function LoopCard({ journey, onNavigate }: { journey: Journey; onNavigate: (path: string) => void }) {
  const [shown, setShown] = useState<string | null>(null)
  const { steps, focus, current } = journey
  const fact = steps.find((s) => s.id === shown)
  const strip = useRef<HTMLDivElement>(null)
  // On a phone the strip scrolls sideways: bring the current step into view (horizontally only).
  useEffect(() => {
    const wrap = strip.current
    const button = wrap?.querySelector<HTMLElement>('.loop-step-current, .loop-step-blocked')
    if (wrap && button) wrap.scrollLeft = Math.max(0, button.offsetLeft - wrap.offsetLeft - 8)
  }, [current.id])
  return (
    <section className="card loop" aria-labelledby="loop-h" data-testid="loop">
      <h2 id="loop-h">Your loop</h2>
      <div className="loop-strip-wrap" ref={strip}>
        <ol className="loop-strip" aria-label="The six steps; tap one for its status">
          {steps.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className={`loop-step loop-step-${s.state}`}
                aria-label={`Step ${s.n}, ${s.label}, ${STATE_WORDS[s.state]}`}
                aria-expanded={shown === s.id}
                aria-controls="loop-fact"
                onClick={() => setShown(shown === s.id ? null : s.id)}
              >
                <span className="loop-num" aria-hidden="true">
                  {s.n}
                </span>
                {s.label}
                {STATE_MARKS[s.state] ? (
                  <span className="loop-mark" aria-hidden="true">
                    {STATE_MARKS[s.state]}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ol>
        <span className="loop-back" aria-hidden="true" title="Learn feeds the next Make">
          ↺
        </span>
      </div>
      <p id="loop-fact" className="loop-fact" aria-live="polite" data-testid="loop-fact">
        {fact ? (
          <>
            <strong>
              {fact.n} · {fact.label}:
            </strong>{' '}
            {fact.fact}
            {fact.mac ? ' (on the Mac)' : ''}
          </>
        ) : null}
      </p>
      <div className={`loop-hero loop-hero-${current.state}`} data-testid="next-step">
        <p className="loop-hero-label">
          Step {current.n} · {current.label}
          {current.state === 'blocked' ? ' · blocked' : ''}
          {current.mac ? ' · on the Mac' : ''}
        </p>
        <p className="loop-hero-title">
          <strong>{focus.title}</strong>
        </p>
        <p className="hint">{focus.detail}</p>
        <div className="actions">
          {focus.action ? (
            <Go className="btn btn-primary" to={focus.action.to} onNavigate={onNavigate}>
              {focus.action.label}
            </Go>
          ) : (
            <Go to="activity" onNavigate={onNavigate}>
              See what was posted →
            </Go>
          )}
        </div>
      </div>
    </section>
  )
}

const ATTENTION_LABELS: Record<AttentionItem['tone'], string> = { bad: 'Problem', warn: 'Check', info: 'Info' }

export function AttentionList({ items, onNavigate }: { items: AttentionItem[]; onNavigate: (path: string) => void }) {
  return (
    <section className="card" aria-labelledby="attention-h" data-testid="attention">
      <h2 id="attention-h">Attention</h2>
      <ul className="row-list">
        {items.map((item) => (
          <li key={item.id} className="row-item">
            <StatusBadge tone={item.tone} label={ATTENTION_LABELS[item.tone]} /> <span>{item.text}</span>{' '}
            <Go to={item.to} onNavigate={onNavigate}>
              {`→ ${item.where}`}
            </Go>
          </li>
        ))}
      </ul>
    </section>
  )
}

const MARK_GLYPHS: Record<Tone, string> = { good: '✓', bad: '✕', warn: '!', info: '•', neutral: '•' }

export function PlatformsCard({ data, rows }: { data: DashboardResponse; rows: PlatformRow[] }) {
  const zone = data.displayTimezone
  const overall = data.statuses.recurringEnabled
  return (
    <section className="card" id="platforms" aria-labelledby="platforms-h" data-testid="platforms">
      <h2 id="platforms-h">Platforms</h2>
      <ul className="row-list">
        {rows.map((row) => {
          const posting = data.statuses.postingTestPassed.platforms[row.platform]
          const auth = data.statuses.currentlyAuthenticated.platforms[row.platform]
          const recurring = data.statuses.recurringEnabled.platforms[row.platform]
          return (
            <li key={row.platform} data-testid="platform-row">
              <details className="platform-item">
                <summary>
                  <span className="platform-name">{row.name}</span>
                  <span className="marks">
                    {row.marks.map((m) => (
                      <span key={m.name} className={`mark mark-${m.tone}`} role="img" aria-label={`${m.name}: ${m.label}`} title={`${m.name}: ${m.label}`}>
                        {MARK_GLYPHS[m.tone]}
                      </span>
                    ))}
                  </span>
                  <span className="platform-summary">{row.summary}</span>
                </summary>
                <dl className="facts">
                  <dt>Posting test</dt>
                  <dd>
                    {posting.label}
                    {posting.passedAt ? (
                      <span className="block muted">
                        <Time iso={posting.passedAt} zone={zone} />
                      </span>
                    ) : null}
                    {posting.permalink ? (
                      <a className="block" href={posting.permalink} target="_blank" rel="noopener noreferrer">
                        Test post
                      </a>
                    ) : null}
                    {posting.detail ? <span className="block">{posting.detail}</span> : null}
                  </dd>
                  <dt>Authenticated</dt>
                  <dd>
                    {row.marks[1].label}
                    {auth.checkedAt ? (
                      <span className="block muted">
                        Checked <Time iso={auth.checkedAt} zone={zone} />
                      </span>
                    ) : null}
                    {auth.expiresAt ? (
                      <span className="block muted">
                        Expires <Time iso={auth.expiresAt} zone={zone} />
                      </span>
                    ) : null}
                    {auth.detail ? <span className="block">{auth.detail}</span> : null}
                  </dd>
                  <dt>Recurring</dt>
                  <dd>
                    {recurring.label}
                    <span className="block muted">
                      Route {recurring.route}; identity {recurring.identityVerified ? 'verified' : 'not verified'}; publishing{' '}
                      {recurring.publishingVerified ? 'verified' : 'not verified'}
                    </span>
                    {recurring.detail ? <span className="block">{recurring.detail}</span> : null}
                  </dd>
                </dl>
              </details>
            </li>
          )
        })}
      </ul>
      <p className="hint">
        Marks, in order: posting test passed · currently authenticated · recurring publishing on. ✓ yes · ! unknown · ✕ no. They are separate
        facts: a passed test does not mean publishing is on. Tap a platform for details.
      </p>
      <p className="muted">
        Recurring publishing overall: {overall.label} · config {overall.configPaused ? 'paused' : 'not paused'} · PAUSED sentinel{' '}
        {overall.pausedSentinel ? 'present' : 'absent'} · publisher timer {overall.publisherTimerEnabled ? 'enabled' : 'disabled'},{' '}
        {overall.publisherTimerActive ? 'active' : 'inactive'}
      </p>
    </section>
  )
}
