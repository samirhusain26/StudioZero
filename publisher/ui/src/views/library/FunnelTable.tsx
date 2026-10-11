import { useId } from 'react'
import type { EpisodeFunnel } from '../../api/types'
import { platformName } from '../../lib/format'
import { countedText, countText, followsSourceText, funnelPlatforms, platformReadText, watchText } from '../../lib/funnel'

/** "—" for a missing number, with words for screen readers; null is "no data", never zero. */
function Cell({ text }: { text: string | null }) {
  if (text !== null) return <>{text}</>
  return (
    <>
      <span aria-hidden="true">—</span>
      <span className="sr-only">no data</span>
    </>
  )
}

/** Per-video funnel (NextBatchInfo.funnel): Views → Avg watch → Engaged → Answered → Follows that day. */
export function FunnelTable({ funnel }: { funnel: EpisodeFunnel[] }) {
  const id = useId()
  return (
    <section className="stack" aria-labelledby={`${id}-h`} data-testid="funnel">
      <h3 id={`${id}-h`} className="h4">
        Per video
      </h3>
      {funnel.length ? (
        <div className="table-wrap">
          <table className="funnel-table">
            <caption className="sr-only">Views, average watch, engaged, answered and follows that day for each posted episode, platforms added up</caption>
            <thead>
              <tr>
                <th scope="col">Episode</th>
                <th scope="col">Views</th>
                <th scope="col">Avg watch</th>
                <th scope="col">Engaged</th>
                <th scope="col">Answered</th>
                <th scope="col">Follows that day</th>
              </tr>
            </thead>
            <tbody>
              {funnel.map((row) => (
                <FunnelRows key={row.episode} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No per-video stats yet. They appear once the Pi has read stats for posted episodes.</p>
      )}
      <p className="hint">
        Follows that day are the account's new followers on the day the video was posted. They are account-level for that day, not attributed to
        the video.
      </p>
      <p className="hint">X and TikTok come from Buffer, which refreshes its numbers once a day; it gives no replies, so Answered stays —.</p>
    </section>
  )
}

function FunnelRows({ row }: { row: EpisodeFunnel }) {
  const platforms = funnelPlatforms(row)
  const counted = countedText(row.counted)
  return (
    <>
      <tr className="funnel-main">
        <th scope="row">
          <code>{row.episode}</code>
          {row.publishedDates.length ? <div className="hint">Posted {row.publishedDates.join(', ')}</div> : null}
        </th>
        <td>
          <Cell text={countText(row.views)} />
        </td>
        <td>
          <Cell text={watchText(row.avgWatchSeconds)} />
        </td>
        <td>
          <Cell text={countText(row.engaged)} />
        </td>
        <td>
          <Cell text={countText(row.answered)} />
        </td>
        <td>
          <Cell text={countText(row.followsThatDay)} />
        </td>
      </tr>
      <tr className="funnel-detail">
        <td colSpan={6}>
          <details className="disclosure">
            <summary>By platform: {row.episode}</summary>
            {counted ? <p className="hint">Totals add up {counted}.</p> : <p className="hint">No platform had numbers for the totals yet.</p>}
            {platforms.length ? (
              <table className="funnel-platforms">
                <caption className="sr-only">{row.episode} by platform</caption>
                <thead>
                  <tr>
                    <th scope="col">Platform</th>
                    <th scope="col">Stats</th>
                    <th scope="col">Views</th>
                    <th scope="col">Avg watch</th>
                    <th scope="col">Engaged</th>
                    <th scope="col">Answered</th>
                    <th scope="col">Follows that day</th>
                  </tr>
                </thead>
                <tbody>
                  {platforms.map(([platform, p]) => {
                    const source = followsSourceText(p.followsSource)
                    const follows = countText(p.followsThatDay)
                    return (
                      <tr key={platform}>
                        <th scope="row">{platformName(platform)}</th>
                        <td>{platformReadText(platform, p)}</td>
                        <td>
                          <Cell text={countText(p.views)} />
                        </td>
                        <td>
                          <Cell text={watchText(p.avgWatchSeconds)} />
                        </td>
                        <td>
                          <Cell text={countText(p.engaged)} />
                        </td>
                        <td>
                          <Cell text={countText(p.answered)} />
                        </td>
                        <td>
                          <Cell text={follows} />
                          {follows !== null && source ? <span className="muted"> ({source})</span> : null}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            ) : (
              <p>No platform posts for this episode.</p>
            )}
          </details>
        </td>
      </tr>
    </>
  )
}
