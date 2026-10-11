import { ApiRequestError } from '../api/client'

export function describeError(error: unknown): { message: string; nextAction: string | null; problems: ApiRequestError['problems'] } {
  if (error instanceof ApiRequestError) return { message: error.message, nextAction: error.nextAction, problems: error.problems }
  if (error instanceof Error) return { message: error.message, nextAction: null, problems: [] }
  return { message: 'Something went wrong.', nextAction: 'Reload the page and try again.', problems: [] }
}

/** Renders the backend's {error, nextAction} (and validation problems) as an alert. */
export function ErrorNotice({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null
  const { message, nextAction, problems } = describeError(error)
  return (
    <div className="notice notice-error" role="alert">
      <p className="notice-title">
        <strong>{title ?? 'Error'}:</strong> {message}
      </p>
      {nextAction ? (
        <p>
          <strong>Next step:</strong> {nextAction}
        </p>
      ) : null}
      {problems.length > 0 ? (
        <ul className="problem-list">
          {problems.map((p, i) => (
            <li key={`${p.path}-${i}`}>
              <code>{p.path}</code>: {p.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
