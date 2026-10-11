import { VIEWS, type ViewId } from '../views'

/**
 * The five sections: a bottom tab bar on phones, a fixed left sidebar from 1024 px (same items, order and icons).
 * Plain links; App handles focus after navigation.
 */
export function AppNav({ current, version, onNavigate }: { current: ViewId | null; version: string | null; onNavigate: (path: string) => void }) {
  return (
    <nav aria-label="Sections" className="app-nav">
      <p className="nav-brand">Scalar publishing</p>
      <ul className="nav-list">
        {VIEWS.map((v) => (
          <li key={v.id}>
            <a
              href={`#/${v.id}`}
              className="nav-link"
              aria-current={v.id === current ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault()
                onNavigate(v.id)
              }}
            >
              <span className="nav-icon" aria-hidden="true">
                {v.icon}
              </span>
              <span className="nav-label">{v.label}</span>
            </a>
          </li>
        ))}
      </ul>
      <p className="nav-foot muted">
        Signed in
        {version ? (
          <>
            {' '}
            · <code>v {version}</code>
          </>
        ) : null}
      </p>
    </nav>
  )
}
