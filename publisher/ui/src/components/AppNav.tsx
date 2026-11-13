import { VIEWS } from '../views'

/**
 * The five sections: a bottom tab bar on phones, a fixed left sidebar from 1024 px (same items, order and icons).
 * Plain links; App handles focus after navigation.
 */
export function AppNav({ current, version, onNavigate }: { current: string | null; version: string | null; onNavigate: (path: string) => void }) {
  return (
    <nav aria-label="Sections" className="app-nav">
      <p className="nav-brand"><img src="/icons/studiozero-64.png" width="32" height="32" alt="" />StudioZero</p>
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
      <ul className="nav-utilities" aria-label="Utilities">
        <li><a className="nav-link" href="#/settings" aria-current={current === 'settings' ? 'page' : undefined} onClick={(e) => { e.preventDefault(); onNavigate('settings') }}>Settings</a></li>
        <li><a className="nav-link" href="#/guide" aria-current={current === 'guide' ? 'page' : undefined} onClick={(e) => { e.preventDefault(); onNavigate('guide') }}>Help</a></li>
        <li><a className="nav-link" href="#/activity" aria-current={current === 'activity' ? 'page' : undefined} onClick={(e) => { e.preventDefault(); onNavigate('activity') }}>Operations</a></li>
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
