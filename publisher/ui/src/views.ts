import { isActivityTab, type ActivityTab } from './lib/activityFilters'

/**
 * The six sections (docs/PI_UI_REDESIGN_PLAN.md §2; Studio added by docs/STUDIO_PLAN.md §1 decision 5), in tab-bar /
 * sidebar order. Icons are plain text glyphs.
 */
export const VIEWS = [
  { id: 'home', label: 'Home', icon: '⌂' },
  { id: 'studio', label: 'Studio', icon: '✎' },
  { id: 'library', label: 'Library', icon: '▣' },
  { id: 'schedule', label: 'Schedule', icon: '▦' },
  { id: 'activity', label: 'Activity', icon: '≡' },
  { id: 'settings', label: 'Settings', icon: '⚙︎' },
] as const

export type ViewId = (typeof VIEWS)[number]['id']

/**
 * A parsed hash route. Sub-routes: `#/studio/make[?project=<id>]`, `#/library/episode/<episodeId>/<revision>`, `#/schedule/queue`,
 * `#/activity?tab=<posts|uploads|approvals|system>`, `#/settings#<section>`, `#/home#platforms` and `#/guide/<anchor>` (the guide is opened from the help icon,
 * not a tab). `redirect` is set for an old hash (`#/dashboard`, `#/history`, `#/activation`, `#/next-batch`, `#/library/make`):
 * the address bar is replaced with it.
 */
export interface Route {
  view: ViewId | 'guide'
  /** Studio › Make a batch. */
  make?: true
  /** Studio › Make a batch for one catalog project (default: the page's own choice). */
  project?: string
  queue?: true
  episode?: { episodeId: string; revision: number }
  tab?: Exclude<ActivityTab, 'all'>
  section?: string
  anchor?: string
  redirect?: string
}

const ANCHOR = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
const PROJECT = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

const OLD: Record<string, { route: Route; hash: string }> = {
  dashboard: { route: { view: 'home' }, hash: '#/home' },
  history: { route: { view: 'activity', tab: 'posts' }, hash: '#/activity?tab=posts' },
  activation: { route: { view: 'settings', section: 'activation' }, hash: '#/settings#activation' },
  'next-batch': { route: { view: 'studio', make: true }, hash: '#/studio/make' },
}

function isView(id: string): id is ViewId {
  return VIEWS.some((v) => v.id === id)
}

function decode(part: string): string | null {
  try {
    return decodeURIComponent(part)
  } catch {
    return null
  }
}

export function routeFromHash(hash: string): Route {
  const raw = hash.replace(/^#\/?/, '')
  const sectionAt = raw.indexOf('#')
  const section = sectionAt >= 0 ? raw.slice(sectionAt + 1) : ''
  const withQuery = sectionAt >= 0 ? raw.slice(0, sectionAt) : raw
  const [path = '', query = ''] = withQuery.split('?')
  const [first = '', ...rest] = path.split('/')
  const old = OLD[first]
  if (old && rest.length === 0) return { ...old.route, redirect: old.hash }
  if (first === 'studio') {
    if (rest.length === 1 && rest[0] === 'make') {
      const project = new URLSearchParams(query).get('project') ?? ''
      return PROJECT.test(project) && project.length <= 40 ? { view: 'studio', make: true, project } : { view: 'studio', make: true }
    }
    return { view: 'studio' }
  }
  if (first === 'library') {
    if (rest.length === 1 && rest[0] === 'make') return { view: 'studio', make: true, redirect: '#/studio/make' }
    if (rest[0] === 'episode' && rest.length === 3) {
      const episodeId = decode(rest[1] ?? '')
      const revision = rest[2] ?? ''
      if (episodeId && /^\d+$/.test(revision)) return { view: 'library', episode: { episodeId, revision: Number(revision) } }
    }
    return { view: 'library' }
  }
  if (first === 'schedule') return rest.length === 1 && rest[0] === 'queue' ? { view: 'schedule', queue: true } : { view: 'schedule' }
  if (first === 'activity') {
    const tab = new URLSearchParams(query).get('tab')
    return isActivityTab(tab) && tab !== 'all' ? { view: 'activity', tab } : { view: 'activity' }
  }
  if (first === 'settings' || first === 'home') return ANCHOR.test(section) ? { view: first, section } : { view: first }
  if (first === 'guide') return rest.length === 1 && ANCHOR.test(rest[0] ?? '') ? { view: 'guide', anchor: rest[0] as string } : { view: 'guide' }
  return { view: isView(first) ? first : 'home' }
}

export function viewFromHash(hash: string): Route['view'] {
  return routeFromHash(hash).view
}

export function episodeHash(episodeId: string, revision: number): string {
  return `#/library/episode/${encodeURIComponent(episodeId)}/${revision}`
}

export function guideHash(anchor: string): string {
  return `#/guide/${anchor}`
}

/** The screen a route shows, for titles, the step line and the help icon. */
export type Screen = 'home' | 'studio' | 'library' | 'make' | 'episode' | 'schedule' | 'queue' | 'activity' | 'settings' | 'guide'

export function screenOf(route: Route): Screen {
  if (route.view === 'studio') return route.make ? 'make' : 'studio'
  if (route.view === 'library') return route.episode ? 'episode' : 'library'
  if (route.view === 'schedule' && route.queue) return 'queue'
  return route.view
}

export const SCREEN_TITLES: Record<Screen, string> = {
  home: 'Home',
  studio: 'Studio',
  library: 'Library',
  make: 'Make a batch',
  episode: 'Episode',
  schedule: 'Schedule',
  queue: 'Approved queue',
  activity: 'Activity',
  settings: 'Settings',
  guide: 'Guide',
}
