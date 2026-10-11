import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ActivityEntry, ActivitySeverity, HistoryResponse, HistoryRow, HistoryStatus, Platform } from '../api/types'
import { ACTIVITY_SEVERITIES, PLATFORMS } from '../api/types'
import { Chip } from '../components/Chip'
import { ErrorNotice } from '../components/ErrorNotice'
import { Loading } from '../components/Loading'
import { RefreshLine } from '../components/RefreshLine'
import { ScreenHelp } from '../components/ScreenHelp'
import { StatusBadge } from '../components/StatusBadge'
import { Time } from '../components/Time'
import { useAutoRefresh, type AutoRefreshState } from '../hooks/useAutoRefresh'
import { ACTIVITY_SEVERITY, groupByDay, mergeHead } from '../lib/activity'
import {
  ACTIVITY_TABS,
  feedQuery,
  matchesSearch,
  menuFilterCount,
  NO_FILTERS,
  postsQuery,
  type ActivityFilters,
  type ActivityTab,
} from '../lib/activityFilters'
import { platformName, shortHash, titleCase } from '../lib/format'
import { LEDGER_STATUS, ledgerStatus } from '../lib/labels'
import { deviceTimeZone, formatDayHeading, formatTimeLocalAndUtc, localDateKey } from '../lib/time'
import { JobDrawer } from './activity/JobDrawer'

const PAGE = 100
const SEARCH_DELAY_MS = 400

export function ActivityView({ tab = 'all', onTab }: { tab?: ActivityTab; onTab: (tab: ActivityTab) => void }) {
  const [filters, setFilters] = useState<ActivityFilters>(NO_FILTERS)
  const [search, setSearch] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  // The search box applies after a short pause in typing (Posts searches on the Pi).
  useEffect(() => {
    const t = window.setTimeout(() => setFilters((f) => (f.q === search ? f : { ...f, q: search })), SEARCH_DELAY_MS)
    return () => window.clearTimeout(t)
  }, [search])

  return (
    <div className="stack-lg">
      <ScreenHelp id="activity" />
      <div className="stack">
        <div className="chip-row" role="group" aria-label="Show">
          {ACTIVITY_TABS.map((t) => (
            <Chip key={t.id} pressed={tab === t.id} onClick={() => onTab(t.id)}>
              {t.label}
            </Chip>
          ))}
        </div>
        <div className="search-row">
          <form role="search" className="search-form" onSubmit={(e) => {
            e.preventDefault()
            setFilters({ ...filters, q: search })
          }}>
            <label htmlFor="a-search" className="sr-only">
              Search
            </label>
            <input
              id="a-search"
              type="search"
              placeholder="Search question id, job id, platform…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </form>
          <MoreMenu tab={tab} filters={filters} setFilters={setFilters} />
        </div>
      </div>
      {tab === 'posts' ? (
        <PostsFeed key="posts" filters={filters} onOpenJob={setJobId} />
      ) : (
        <TimelineFeed key={tab} tab={tab} filters={filters} onOpenJob={setJobId} />
      )}
      {jobId ? <JobDrawer jobId={jobId} onClose={() => setJobId(null)} /> : null}
    </div>
  )
}

/** ⋯ : the filters that are not chips, plus export. Closed by default, so the default view shows no form fields. */
function MoreMenu({ tab, filters, setFilters }: { tab: ActivityTab; filters: ActivityFilters; setFilters: (f: ActivityFilters) => void }) {
  const posts = tab === 'posts'
  const count = menuFilterCount(tab, filters)
  const [exportStatus, setExportStatus] = useState('')
  const [exportError, setExportError] = useState<unknown>(null)
  const exportAs = async (format: 'csv' | 'json') => {
    setExportError(null)
    setExportStatus(`Preparing ${format.toUpperCase()}…`)
    try {
      const name = posts ? await api.exportHistory(postsQuery(filters), format) : await api.exportActivity(feedQuery(tab, filters), format)
      setExportStatus(`Downloaded ${name}.`)
    } catch (e) {
      setExportStatus('')
      setExportError(e)
    }
  }
  return (
    <details className="menu">
      <summary aria-label={`Filters and export${count ? ` (${count} set)` : ''}`}>
        <span aria-hidden="true">⋯</span>
        {count ? <span className="menu-count">{count}</span> : null}
      </summary>
      <div className="menu-panel stack">
        <div className="field">
          <label htmlFor="a-platform">Platform</label>
          <select id="a-platform" value={filters.platform} onChange={(e) => setFilters({ ...filters, platform: e.target.value as Platform | '' })}>
            <option value="">All</option>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {platformName(p)}
              </option>
            ))}
          </select>
        </div>
        {posts ? (
          <>
            <div className="field">
              <label htmlFor="a-status">Status</label>
              <select id="a-status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value as HistoryStatus | '' })}>
                <option value="">All</option>
                {Object.entries(LEDGER_STATUS)
                  .filter(([id]) => id !== 'not-enqueued')
                  .map(([id, s]) => (
                    <option key={id} value={id}>
                      {s.label}
                    </option>
                  ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="a-from">From (local date)</label>
              <input id="a-from" type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="a-to">To (local date)</label>
              <input id="a-to" type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} />
            </div>
          </>
        ) : (
          <div className="field">
            <label htmlFor="a-severity">Severity</label>
            <select id="a-severity" value={filters.severity} onChange={(e) => setFilters({ ...filters, severity: e.target.value as ActivitySeverity | '' })}>
              <option value="">All</option>
              {ACTIVITY_SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {ACTIVITY_SEVERITY[s].label}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="actions">
          <button type="button" className="btn" disabled={!count} onClick={() => setFilters({ ...NO_FILTERS, q: filters.q })}>
            Clear filters
          </button>
          <button type="button" className="btn" onClick={() => void exportAs('csv')}>
            Export CSV
          </button>
          <button type="button" className="btn" onClick={() => void exportAs('json')}>
            Export JSON
          </button>
        </div>
        <p role="status" aria-live="polite" className="muted">
          {exportStatus}
        </p>
        <ErrorNotice error={exportError} title="Export failed" />
      </div>
    </details>
  )
}

function Refresh<T>({ state, zone }: { state: AutoRefreshState<T>; zone: string }) {
  return (
    <RefreshLine
      updatedAt={state.updatedAt}
      zone={zone}
      auto={state.auto}
      onToggle={state.setAuto}
      onRefresh={state.reload}
      loading={state.loading}
      stopped={state.stopped}
    />
  )
}

function NothingPosted() {
  return (
    <p>
      Nothing has been posted. Posts appear once an approved schedule runs, and activation is the owner’s command:{' '}
      <a href="#/settings#activation">Settings › Activation →</a>
    </p>
  )
}

interface Older {
  key: string
  entries: ActivityEntry[]
  cursor: string | null
}

function TimelineFeed({ tab, filters, onOpenJob }: { tab: ActivityTab; filters: ActivityFilters; onOpenJob: (jobId: string) => void }) {
  const query = feedQuery(tab, filters)
  const key = JSON.stringify(query)
  const head = useAutoRefresh((signal) => api.activity({ ...query, limit: PAGE }, signal), key)
  const [older, setOlder] = useState<Older>({ key, entries: [], cursor: null })
  const [olderBusy, setOlderBusy] = useState(false)
  const [olderError, setOlderError] = useState<unknown>(null)

  // Older pages belong to one filter set; a new filter starts again from the newest page.
  const olderPages = older.key === key ? older : { key, entries: [], cursor: null }
  const data = head.data
  const zone = data?.displayTimezone ?? deviceTimeZone()
  const loaded = data ? mergeHead(data.entries, olderPages.entries, data.nextBefore === null) : []
  const entries = loaded.filter((e) => matchesSearch(e, filters.q))
  const cursor = olderPages.entries.length ? olderPages.cursor : (data?.nextBefore ?? null)
  const filtered = key !== '{}' || filters.q.trim() !== ''

  const loadOlder = async () => {
    if (!cursor) return
    setOlderBusy(true)
    setOlderError(null)
    try {
      const page = await api.activity({ ...query, limit: PAGE, before: cursor })
      setOlder({ key, entries: [...olderPages.entries, ...page.entries], cursor: page.nextBefore })
    } catch (e) {
      setOlderError(e)
    } finally {
      setOlderBusy(false)
    }
  }

  return (
    <>
      <Refresh state={head} zone={zone} />
      <ErrorNotice error={head.error} title="Activity unavailable" />
      <section aria-labelledby="feed-h" className="stack" data-testid="activity-feed">
        <h2 id="feed-h" className="sr-only">
          Timeline
        </h2>
        {!data && head.loading ? <Loading /> : null}
        {data && entries.length === 0 ? (
          filtered ? (
            <p>Nothing matches. Clear the search or the filters under ⋯ to see everything.</p>
          ) : tab === 'all' ? (
            <NothingPosted />
          ) : (
            <p>Nothing of this kind yet.</p>
          )
        ) : null}
        {groupByDay(entries, zone).map((day) => (
          <section key={day.dateKey} className="activity-day" aria-labelledby={`day-${day.dateKey}`}>
            <h3 id={`day-${day.dateKey}`} className="day-heading">
              {formatDayHeading(day.dateKey)}
            </h3>
            <ol className="activity-list">
              {day.entries.map((entry) => (
                <ActivityItem key={entry.id} entry={entry} zone={zone} onOpenJob={onOpenJob} />
              ))}
            </ol>
          </section>
        ))}
        {data ? (
          <div className="actions">
            {cursor ? (
              <button type="button" className="btn" onClick={() => void loadOlder()} disabled={olderBusy}>
                {olderBusy ? 'Loading…' : 'Load older'}
              </button>
            ) : loaded.length ? (
              <p className="muted">No older activity.</p>
            ) : null}
          </div>
        ) : null}
        <ErrorNotice error={olderError} title="Older activity unavailable" />
      </section>
    </>
  )
}

export function ActivityItem({ entry, zone, onOpenJob }: { entry: ActivityEntry; zone: string; onOpenJob: (jobId: string) => void }) {
  const severity = ACTIVITY_SEVERITY[entry.severity]
  const jobId = entry.jobId
  const meta = [
    entry.platform ? platformName(entry.platform) : null,
    entry.jobKind && entry.jobKind !== 'post' ? titleCase(entry.jobKind) : null,
    entry.episode ?? entry.episodeId,
    entry.batchId && !entry.episode ? `batch ${entry.batchId}` : null,
    entry.draftSha256 ? `draft ${shortHash(entry.draftSha256)}` : null,
    entry.manifestSha256 ? `manifest ${shortHash(entry.manifestSha256)}` : null,
  ].filter(Boolean)
  return (
    <li className={`activity-item activity-${entry.severity}`} data-testid="activity-entry">
      <p className="activity-time">
        <time dateTime={entry.at}>{formatTimeLocalAndUtc(entry.at, zone)}</time>
      </p>
      <div className="activity-main">
        <p className="row-head">
          <StatusBadge tone={severity.tone} label={severity.label} />
          {jobId ? (
            <button type="button" className="link-button" onClick={() => onOpenJob(jobId)} aria-haspopup="dialog">
              {entry.title}
            </button>
          ) : (
            <strong>{entry.title}</strong>
          )}
        </p>
        {entry.detail ? <p className="activity-detail">{entry.detail}</p> : null}
        {meta.length ? <p className="muted activity-meta">{meta.join(' · ')}</p> : null}
        {entry.permalink ? (
          <p>
            <a href={entry.permalink} target="_blank" rel="noopener noreferrer">
              View the post
            </a>
          </p>
        ) : null}
      </div>
    </li>
  )
}

const SEVERITY_OF_TONE = { good: 'success', bad: 'error', warn: 'warning', info: 'info', neutral: 'info' } as const

/** When a post row happened: published time when known, else its slot. */
function postAt(row: HistoryRow): string {
  return row.publishedAt ?? row.slotUtc
}

function PostsFeed({ filters, onOpenJob }: { filters: ActivityFilters; onOpenJob: (jobId: string) => void }) {
  const query = postsQuery(filters)
  const key = JSON.stringify(query)
  const state = useAutoRefresh<HistoryResponse>(() => api.history(query), key)
  const [layout, setLayout] = useState<'timeline' | 'table'>('timeline')
  const data = state.data
  const zone = data?.displayTimezone ?? deviceTimeZone()
  const days: { dateKey: string; rows: HistoryRow[] }[] = []
  for (const row of data?.rows ?? []) {
    const k = localDateKey(postAt(row), zone)
    const last = days[days.length - 1]
    if (last && last.dateKey === k) last.rows.push(row)
    else days.push({ dateKey: k, rows: [row] })
  }
  return (
    <>
      <Refresh state={state} zone={zone} />
      <ErrorNotice error={state.error} title="Posts unavailable" />
      <section aria-labelledby="posts-h" className="stack" data-testid="history-results">
        <div className="row-head">
          <h2 id="posts-h" className="sr-only">
            Posts
          </h2>
          <div role="status" aria-live="polite">
            {state.loading && !data ? (
              <Loading />
            ) : data ? (
              <p className="muted">{data.truncated ? `Showing ${data.rows.length} of ${data.total} jobs.` : `${data.total} job${data.total === 1 ? '' : 's'}.`}</p>
            ) : null}
          </div>
          {data && data.rows.length ? (
            <div className="segmented desktop-only" role="group" aria-label="Layout">
              <Chip pressed={layout === 'timeline'} onClick={() => setLayout('timeline')}>
                Timeline
              </Chip>
              <Chip pressed={layout === 'table'} onClick={() => setLayout('table')}>
                Table
              </Chip>
            </div>
          ) : null}
        </div>
        {data && data.rows.length === 0 && !state.loading ? (
          key === '{}' ? <NothingPosted /> : <p>No posts match. Clear the search or the filters under ⋯ and try again.</p>
        ) : null}
        {data && data.rows.length && layout === 'table' ? <PostsTable data={data} onOpenJob={onOpenJob} /> : null}
        {data && (layout === 'timeline' || !data.rows.length)
          ? days.map((day) => (
              <section key={day.dateKey} className="activity-day" aria-labelledby={`pday-${day.dateKey}`}>
                <h3 id={`pday-${day.dateKey}`} className="day-heading">
                  {formatDayHeading(day.dateKey)}
                </h3>
                <ol className="activity-list">
                  {day.rows.map((row) => (
                    <PostItem key={row.jobId} row={row} zone={zone} onOpenJob={onOpenJob} />
                  ))}
                </ol>
              </section>
            ))
          : null}
      </section>
    </>
  )
}

export function PostItem({ row, zone, onOpenJob }: { row: HistoryRow; zone: string; onOpenJob: (jobId: string) => void }) {
  const status = ledgerStatus(row.status)
  return (
    <li className={`activity-item activity-${SEVERITY_OF_TONE[status.tone]}`} data-testid="post-entry">
      <p className="activity-time">
        <time dateTime={postAt(row)}>{formatTimeLocalAndUtc(postAt(row), zone)}</time>
      </p>
      <div className="activity-main">
        <p className="row-head">
          <StatusBadge tone={status.tone} label={row.statusLabel || status.label} />
          <strong>
            {platformName(row.platform)}
            {row.kind !== 'post' ? ` ${titleCase(row.kind)}` : ''}
          </strong>
        </p>
        <p className="muted activity-meta">
          <code>{row.episode}</code>
          {row.episodeId ? ` · ${row.episodeId}` : ''}
          {row.publishedAt ? null : ' · slot'}
        </p>
        {row.captionPreview ? <p className="exact-text clamp">{row.captionPreview}</p> : null}
        {row.error ? (
          <p>
            <strong>{row.error.title}.</strong> {row.error.detail}
          </p>
        ) : null}
        <p className="inline">
          {row.permalink ? (
            <a href={row.permalink} target="_blank" rel="noopener noreferrer">
              View the post
            </a>
          ) : null}
          <button type="button" className="link-button" onClick={() => onOpenJob(row.jobId)} aria-haspopup="dialog">
            Details<span className="sr-only"> for {shortHash(row.jobId)}</span>
          </button>
        </p>
      </div>
    </li>
  )
}

function PostsTable({ data, onOpenJob }: { data: HistoryResponse; onOpenJob: (jobId: string) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">Posts, newest first</caption>
        <thead>
          <tr>
            <th scope="col">Slot ({data.displayTimezone} · UTC)</th>
            <th scope="col">Platform</th>
            <th scope="col">Status</th>
            <th scope="col">Episode</th>
            <th scope="col">Caption</th>
            <th scope="col">Result</th>
            <th scope="col">
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => {
            const status = ledgerStatus(row.status)
            return (
              <tr key={row.jobId}>
                <td>
                  <Time iso={row.slotUtc} zone={data.displayTimezone} />
                </td>
                <td>
                  {platformName(row.platform)}
                  {row.kind !== 'post' ? <span className="block muted">{titleCase(row.kind)}</span> : null}
                </td>
                <td>
                  <StatusBadge tone={status.tone} label={row.statusLabel || status.label} />
                </td>
                <td>
                  <code>{row.episode}</code>
                  {row.episodeId ? <span className="block muted">{row.episodeId}</span> : null}
                </td>
                <td className="cell-caption">{row.captionPreview}</td>
                <td>
                  {row.permalink ? (
                    <a href={row.permalink} target="_blank" rel="noopener noreferrer">
                      Permalink
                    </a>
                  ) : row.error ? (
                    row.error.title
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <button type="button" className="btn" onClick={() => onOpenJob(row.jobId)}>
                    Details<span className="sr-only"> for {shortHash(row.jobId)}</span>
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
