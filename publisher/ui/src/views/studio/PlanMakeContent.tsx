import { useId, useMemo, useState } from 'react'
import type { Catalog, CatalogProject } from '../../api/types'
import { CopyBlock } from '../../components/CopyBlock'
import { readProjectChecks, writeProjectChecks } from '../../lib/makeChecklist'
import { buildPlanBrief, buildPlanPrompt, defaultPlan, planProblems, type BatchPlan } from '../../lib/promptBuilder'
import { copyText } from '../../lib/saveFile'
import { MakeStep as Step } from '../../components/MakeStep'
import { PromptBuilderForm } from './PromptBuilderForm'

const STUDIO_FOLDER = 'cd ~/Personal/code_projects/StudioZero && claude'

/** The first batch id of the month for a project without numbered batches: `YYYY-MM-<project>-01`. */
export function suggestedBatchId(project: string, now: Date = new Date()): string {
  return `${now.toISOString().slice(0, 7)}-${project}-01`
}

/**
 * Studio › Make a batch for a project without games (Originals): build the prompt here, make it with Claude Code and
 * the story engine on the laptop, upload once the Pi validates its contract version.
 */
export function PlanMakeContent({ catalog, project, now }: { catalog: Catalog; project: CatalogProject; now?: Date }) {
  const id = useId()
  const [plan, setPlan] = useState<BatchPlan>(() => defaultPlan(catalog, project.id, suggestedBatchId(project.id, now)))
  const template = useMemo(() => buildPlanBrief(catalog, plan, null), [catalog, plan])
  const [edited, setEdited] = useState<string | null>(null)
  const brief = edited ?? template
  const problems = planProblems(catalog, plan)
  const [status, setStatus] = useState('')
  const checks = useMemo(() => [...project.checks, { id: 'finalize', name: 'Finalize (only on your approval)' }], [project.checks])
  const known = checks.map((c) => c.id)
  const [ticked, setTicked] = useState<string[]>(() => readProjectChecks(project.id, plan.batchId, known))

  const setBatchId = (batchId: string) => {
    setPlan({ ...plan, batchId })
    setTicked(readProjectChecks(project.id, batchId, known))
  }
  const tick = (check: string, on: boolean) => {
    const next = known.filter((k) => (k === check ? on : ticked.includes(k)))
    setTicked(next)
    writeProjectChecks(project.id, plan.batchId, next)
  }
  const copy = async () => {
    const ok = await copyText(buildPlanPrompt(catalog, plan, brief))
    setStatus(ok ? 'Prompt copied. Paste it into Claude Code in the StudioZero folder (step 2).' : 'Copy failed: select the brief and copy it by hand.')
  }

  return (
    <div className="make-layout">
      <div className="stack-lg">
        <Step n={1} title="Write the brief" where="Pi">
          <div className="field">
            <label htmlFor={`${id}-batch`}>Batch id</label>
            <input id={`${id}-batch`} value={plan.batchId} maxLength={64} onChange={(e) => setBatchId(e.target.value.trim())} />
          </div>
          <PromptBuilderForm catalog={catalog} plan={plan} onChange={setPlan} />
          <div className="field">
            <label htmlFor={`${id}-brief`}>Brief (Markdown)</label>
            <textarea id={`${id}-brief`} rows={14} className="brief-text" value={brief} onChange={(e) => setEdited(e.target.value)} />
          </div>
          <div className="actions">
            <button type="button" className="btn btn-quiet" onClick={() => setEdited(null)} disabled={edited === null}>
              Reset to template
            </button>
          </div>
          {problems.length ? (
            <div className="notice notice-warn" data-testid="plan-problems">
              <p>Fix these first:</p>
              <ul>
                {problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={() => void copy()} disabled={problems.length > 0}>
              Copy prompt for Claude
            </button>
          </div>
          <p className="hint">The prompt ends with the fixed safety lines: nothing is finalized, uploaded or paid for without your OK.</p>
          <p role="status" aria-live="polite" className="muted">
            {status}
          </p>
        </Step>
      </div>
      <div className="stack-lg">
        <Step n={2} title="Let Claude make it" where="Mac" testId="make-checklist">
          <ol className="steps">
            <li>
              Start Claude in the StudioZero folder on the laptop:
              <CopyBlock label="On the laptop" code={STUDIO_FOLDER} />
            </li>
            <li>Paste the prompt. Claude shows a cost estimate before any paid step and waits for your OK. Tick each check as you approve it (kept only in this browser):</li>
          </ol>
          <fieldset className="stack make-checks">
            <legend className="sr-only">Checks for {plan.batchId}</legend>
            {checks.map((c) => (
              <div key={c.id} className="field-check">
                <input id={`${id}-${c.id}`} type="checkbox" checked={ticked.includes(c.id)} onChange={(e) => tick(c.id, e.target.checked)} />
                <label htmlFor={`${id}-${c.id}`}>{c.name}</label>
              </div>
            ))}
          </fieldset>
        </Step>
        <Step n={3} title="Upload it" where="Pi">
          <p>
            {project.name} batches use contract v{project.contractSchemaVersion}. Upload the finalized batch folder in Library › Add batch; the Pi
            validates it with the same contract and its {project.name} rules, then you review and approve each episode.
          </p>
        </Step>
      </div>
    </div>
  )
}
