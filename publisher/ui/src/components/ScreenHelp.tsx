import { SCREEN_HELP, type ScreenHelpId } from '../lib/help'
import { guideHash } from '../views'

/** Collapsible "What to do here" with a link to the matching guide section. */
export function ScreenHelp({ id }: { id: ScreenHelpId }) {
  const help = SCREEN_HELP[id]
  return (
    <details className="screen-help" data-testid="screen-help">
      <summary>What to do here</summary>
      <ul className="screen-help-lines">
        {help.lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p>
        <a href={guideHash(help.anchor)}>More in the Guide →</a>
      </p>
    </details>
  )
}
