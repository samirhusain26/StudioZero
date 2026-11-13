import { useEffect, useMemo, useRef, useState } from 'react'
import { creationApi, type Production } from '../../api/creation'

const EXAMPLES: Record<string, string> = {
  scalargame: 'Make a six-question country quiz about flags and capitals. Use one correct answer and three plausible choices per question.',
  explainers: 'How do noise-cancelling headphones quiet a steady hum? Explain the principle with evidence a curious viewer can check.',
  marathon: 'This week I want to tell the real story of the run. Use only the notes and footage I provide; keep my face and home private.',
  originals: 'A short recap idea. Originals production is on hold; do not generate until I explicitly authorize a run and see its cost estimate.',
}
const PROJECT_NAMES: Record<string, string> = { scalargame: 'Scalargame', explainers: 'Explainers', marathon: 'Marathon', originals: 'Originals' }
const DEFAULT_EXAMPLE = 'Make a six-question country quiz about flags and capitals. Use one correct answer and three plausible choices per question.'

function makePrompt(production: Production) {
  const skill: Record<string, string> = { scalargame: '/video-batch', explainers: '/explainer', marathon: '/marathon-week', originals: '/originals' }
  const current = production.revisions.find((r) => r.id === production.currentRevisionId)
  const feedback = production.decisions.filter((d) => d.revisionId === production.currentRevisionId).flatMap((d) => d.feedback ?? []).map((f) => f.text)
  const researchContext = production.project === 'explainers' ? `\nSaved research context (version ${production.research.version ?? 0}):\n${JSON.stringify(production.research, null, 2)}\n${production.research.status !== 'accepted' ? 'Research is not accepted. Research only; do not make or return a cut until the owner accepts the evidence and angle.' : 'Preserve the accepted question, angle and sources. Required project checkpoints still apply.'}\n` : ''
  return `Continue StudioZero production ${production.id} for ${PROJECT_NAMES[production.project]}.\n\nBrief:\n${production.brief}\n${production.title ? `\nWorking title: ${production.title}\n` : ''}${production.options ? `\nPreferences: ${JSON.stringify(production.options)}\n` : ''}${current ? `\nRevision target: production=${production.id}; revision=${current.id}; batch=${current.manifest.batchId ?? '(not assigned)'}; episode=${current.manifest.episodeId ?? '(not assigned)'}. Revise this production; do not start another.\n` : ''}${feedback.length ? `\nLatest owner feedback:\n${feedback.map((f) => `- ${f}`).join('\n')}\n` : ''}${researchContext}\nUse the current repository skill ${skill[production.project]}. Run required project checks and stop at every owner checkpoint; never infer approval. Use existing local tools only. Preserve prior artifacts. Explainers C2/C3/C4 and Marathon's three checkpoints require explicit owner words. The local whisper voice and creative pilot remain unaccepted. Return actual files and manifest.json exactly shaped like: {"productionId":"${production.id}","project":"${production.project}","revisionId":"safe-unique-id","batchId":${JSON.stringify(current?.manifest.batchId ?? null)},"episodeId":${JSON.stringify(current?.manifest.episodeId ?? null)},"files":[{"path":"cut.mp4","size":123,"sha256":"64 lowercase hex characters","mediaType":"video/mp4","role":"video"}]}. SHA-256 covers exact file bytes. Do not invent passed checks. Do not finalize, publish, schedule, commit, or spend money. ${production.project === 'originals' ? 'STOP: Originals is on hold; do not generate without owner authorization and a displayed cost estimate.' : ''} ${production.project === 'marathon' ? 'Keep private health inputs and footage local; this project is manual delivery.' : ''} ${production.project === 'explainers' ? 'Start with owner-supplied topic research; record the original question and proposed angle. Hold if evidence does not support the story. Return local artifacts only.' : ''}`
}

function draftValue(project: string, field: string) {
  try { return sessionStorage.getItem(`studiozero-${field}:${project}`) ?? '' } catch { return '' }
}

function saveDraft(project: string, field: string, value: string) {
  try { sessionStorage.setItem(`studiozero-${field}:${project}`, value) } catch { /* The current form remains usable when storage is blocked. */ }
}

function stableCreateId(project: string) {
  const key = `studiozero-create-id:${project}`
  try {
    const existing = sessionStorage.getItem(key)
    if (existing) return existing
    const id = `prod-${crypto.randomUUID()}`
    sessionStorage.setItem(key, id)
    return id
  } catch { return `prod-${crypto.randomUUID()}` }
}
async function sha256(file: File) {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)].map((v) => v.toString(16).padStart(2, '0')).join('')
}

export function CreationWorkspace({ project = 'scalargame', productionId }: { project?: string | undefined; productionId?: string | undefined }) {
  const [productions, setProductions] = useState<Production[]>([])
  const [production, setProduction] = useState<Production | null>(null)
  const [createId] = useState(() => stableCreateId(project))
  const [brief, setBrief] = useState(() => { try { return sessionStorage.getItem(`studiozero-brief:${project}`) ?? '' } catch { return '' } })
  const [title, setTitle] = useState(() => draftValue(project, 'title'))
  const [preferences, setPreferences] = useState(() => draftValue(project, 'preferences'))
  const [selectedVideo, setSelectedVideo] = useState('')
  const [error, setError] = useState('')
  const errorNotice = useRef<HTMLParagraphElement>(null)
  useEffect(() => { if (error) errorNotice.current?.focus() }, [error])
  const [productionLoading, setProductionLoading] = useState(Boolean(productionId))
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [manifestFile, setManifestFile] = useState<File | null>(null)
  const [feedback, setFeedback] = useState('')
  const [question, setQuestion] = useState('')
  const [angle, setAngle] = useState('')
  const [sourceText, setSourceText] = useState('')
  const [deliveryUrl, setDeliveryUrl] = useState('')

  const reload = async () => { const result = await creationApi.list(); setProductions(result.productions) }
  useEffect(() => {
    let live = true
    void creationApi.list().then((result) => { if (live) setProductions(result.productions) }).catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : 'Could not load productions.') })
    return () => { live = false }
  }, [])
  useEffect(() => {
    let live = true
    if (productionId) void creationApi.get(productionId).then((p) => {
      if (live) {
        if (p.project !== project) throw new Error('The saved production belongs to a different project.')
        setProduction(p)
        setProductionLoading(false)
        if (p.project === 'explainers') {
          setQuestion(p.research.question ?? p.brief)
          setAngle(p.research.angle ?? '')
          setSourceText((p.research.sources ?? []).join('\n'))
        }
      }
    }).catch((e: unknown) => { if (live) { setProductionLoading(false); setError(e instanceof Error ? e.message : 'Could not load production.') } })
    return () => { live = false }
  }, [productionId, project])
  useEffect(() => {
    let live = true
    if (!productionId) void creationApi.get(createId).then((p) => {
      if (!live) return
      if (p.project !== project) throw new Error('The saved production belongs to a different project.')
      setProduction(p)
      for (const field of ['brief', 'title', 'preferences']) saveDraft(project, field, '')
      try { sessionStorage.removeItem(`studiozero-create-id:${project}`) } catch { /* current form remains available */ }
      if (p.project === 'explainers') {
        setQuestion(p.research.question ?? p.brief)
        setAngle(p.research.angle ?? '')
        setSourceText((p.research.sources ?? []).join('\n'))
      }
      setNotice('Recovered your saved production from the server.')
      window.history.replaceState(null, '', `#/studio/create?project=${encodeURIComponent(project)}&production=${encodeURIComponent(p.id)}`)
    }).catch(() => {})
    return () => { live = false }
  }, [createId, project, productionId])

  const prompt = useMemo(() => production ? makePrompt(production) : '', [production])
  const active = production?.revisions.find((r) => r.id === production.currentRevisionId) ?? null
  const videos = active?.artifacts.filter((a) => a.role === 'video') ?? []
  const video = videos.find((a) => a.path === selectedVideo) ?? videos[0]
  const videoUrl = video && active && production ? `/api/creation/${encodeURIComponent(production.id)}/media/${encodeURIComponent(active.id)}/${encodeURIComponent(video.path)}` : ''
  const artifactUrl = (revisionId: string, path: string) => production ? `/api/creation/${encodeURIComponent(production.id)}/media/${encodeURIComponent(revisionId)}/${encodeURIComponent(path)}` : ''
  const held = production?.project === 'explainers' && production.research.status !== 'accepted'
  const originals = project === 'originals' || production?.project === 'originals'

  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const saved = await creationApi.create({ id: createId, project, brief: brief.trim(), ...(title.trim() ? { title: title.trim() } : {}), options: { preferences } })
      setProduction(saved); setBrief(saved.brief); setNotice('Brief saved to this production on the server.')
      for (const field of ['brief', 'title', 'preferences']) saveDraft(project, field, '')
      if (project === 'explainers') setQuestion(saved.research.question ?? saved.brief)
      try { sessionStorage.removeItem(`studiozero-create-id:${project}`) } catch { /* storage may be unavailable */ }
      window.history.replaceState(null, '', `#/studio/create?project=${encodeURIComponent(project)}&production=${encodeURIComponent(saved.id)}`)
      await reload().catch(() => setNotice('Brief saved. The production list could not refresh; reload this page to see it.'))
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not save the brief.') }
    finally { setBusy(false) }
  }

  async function copyPrompt() {
    try { await navigator.clipboard.writeText(prompt); setCopied(true); setNotice('Prompt copied. Waiting for files; no agent is connected.') }
    catch { setCopied(false); setNotice('Clipboard access failed. Select the prompt below and copy it manually.') }
  }

  async function importCut(event: React.FormEvent) {
    event.preventDefault()
    if (!production || !manifestFile || !files.length) return
    if (production.project === 'originals' || held) return
    setBusy(true); setError(''); setNotice('')
    try {
      const parsed: unknown = JSON.parse(await manifestFile.text())
      if (!parsed || typeof parsed !== 'object') throw new Error('Manifest must be a JSON object.')
      const manifest = parsed as { productionId?: unknown; project?: unknown; revisionId?: unknown; batchId?: unknown; episodeId?: unknown; files?: unknown }
      if (manifest.productionId !== production.id || manifest.project !== production.project || typeof manifest.revisionId !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(manifest.revisionId)) throw new Error('Manifest production, project, or revision identity does not match.')
      for (const key of ['batchId', 'episodeId'] as const) if (manifest[key] != null && (typeof manifest[key] !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(manifest[key]))) throw new Error(`Manifest ${key} is invalid.`)
      if (!Array.isArray(manifest.files) || !manifest.files.length) throw new Error('Manifest needs a file list.')
      if (files.length !== manifest.files.length) throw new Error('Select every file listed in the manifest, without extras.')
      const returned: Array<Record<string, unknown>> = []
      for (const entry of manifest.files as Array<Record<string, unknown>>) {
        const file = files.find((candidate) => candidate.name === entry.path)
        if (!file || entry.size !== file.size || entry.mediaType !== file.type || entry.sha256 !== await sha256(file) || typeof entry.role !== 'string') throw new Error(`Manifest size, hash, media type, or role does not match ${String(entry.path)}.`)
        const staged = await creationApi.stage(production.id, file, file.name)
        returned.push({ ...entry, fileId: staged.fileId })
      }
      if (!returned.some((item) => item.role === 'video' && item.mediaType === 'video/mp4')) throw new Error('The manifest must include an MP4 cut with the video role.')
      const saved = await creationApi.revise(production.id, production.currentRevisionId, { ...manifest, files: returned }, production.research.version ?? 0)
      setProduction(saved); setFiles([]); setManifestFile(null); setNotice('New cut validated and saved. Previous revisions remain in history.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Cut import failed. The current revision remains available.') }
    finally { setBusy(false) }
  }

  async function decide(decision: 'approve-cut' | 'request-revision') {
    if (!production?.currentRevisionId) return
    setBusy(true); setError('')
    try {
      const saved = await creationApi.decide(production.id, production.currentRevisionId, decision, feedback.trim() ? [{ text: feedback.trim() }] : undefined, production.research.version ?? 0)
      setProduction(saved); setNotice(decision === 'approve-cut' ? 'Cut approval recorded for this exact revision. Publishing package approval is separate.' : 'Revision requested. The current cut remains playable.')
      if (decision === 'request-revision') setFeedback('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Decision was not recorded.') }
    finally { setBusy(false) }
  }

  async function research(status: 'held' | 'accepted') {
    if (!production) return
    setBusy(true); setError('')
    try { setProduction(await creationApi.research(production.id, production.research.version ?? 0, status, question, angle, sourceText.split('\n').map((s) => s.trim()).filter(Boolean))); setNotice(status === 'accepted' ? 'Research decision saved. Source checks and required project reviews still apply.' : 'Topic held with its evidence context; cuts remain blocked.') }
    catch (e) { setError(e instanceof Error ? e.message : 'Research decision was not saved.') }
    finally { setBusy(false) }
  }

  async function recordDelivery(event: React.FormEvent) {
    event.preventDefault()
    if (!production?.currentRevisionId) return
    setBusy(true); setError('')
    try {
      setProduction(await creationApi.manualDelivery(production.id, production.currentRevisionId, deliveryUrl.trim() || undefined))
      setNotice('Owner-reported manual delivery saved. This is not platform confirmation.')
    } catch (e) { setError(e instanceof Error ? e.message : 'Manual delivery report was not saved.') }
    finally { setBusy(false) }
  }

  return <div className="creation-workspace">
    <p><a href="#/home">← Studio</a></p>
    <h2>{production ? (production.title || production.brief.slice(0, 72)) : `New ${PROJECT_NAMES[project] ?? project} production`}</h2>
    {!production && productionId && productionLoading ? <p role="status">Loading this production…</p> : null}
    {!production && productionId && !productionLoading ? <p className="notice notice-warn" role="alert">This production could not be loaded. Return to Studio and choose a saved production.</p> : null}
    {!production && !productionId ? <form className="card creation-form" onSubmit={start} aria-labelledby="brief-heading">
      <h3 id="brief-heading">{project === 'explainers' ? 'What should we explain?' : 'What should we make?'}</h3>
      <label htmlFor="creation-brief">Brief <span aria-hidden="true">*</span></label>
      <textarea id="creation-brief" name="brief" value={brief} onChange={(e) => { setBrief(e.target.value); try { sessionStorage.setItem(`studiozero-brief:${project}`, e.target.value) } catch { /* current form remains available */ } }} required maxLength={12000} rows={4} aria-describedby="brief-example" />
      <p className="muted">{brief ? 'Unsaved in this tab · not yet on the server' : 'A saved brief is stored with this production.'}</p>
      <p id="brief-example" className="muted">Example: {EXAMPLES[project] ?? DEFAULT_EXAMPLE}</p>
      <button className="btn" type="button" onClick={() => { const example = EXAMPLES[project] ?? DEFAULT_EXAMPLE; setBrief(example); try { sessionStorage.setItem(`studiozero-brief:${project}`, example) } catch { /* current form remains available */ } }}>Use example</button>
      <details><summary>Optional details</summary><label htmlFor="creation-title">Working title</label><input id="creation-title" name="title" value={title} onChange={(e) => { setTitle(e.target.value); saveDraft(project, 'title', e.target.value) }} maxLength={160} /><label htmlFor="creation-preferences">Creative preferences</label><textarea id="creation-preferences" value={preferences} onChange={(e) => { setPreferences(e.target.value); saveDraft(project, 'preferences', e.target.value) }} maxLength={500} rows={2} /></details>
      {originals ? <p className="notice notice-warn">Originals is on hold. This saves a brief only; no generation can start here.</p> : null}
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save brief and prepare prompt'}</button>
    </form> : production ? <>
      <details><summary>Production identity</summary><code>{production.id}</code><p>{production.currentRevisionId || 'Waiting for files'}</p></details>
      {active && video ? <section className="card stack" aria-labelledby="cut-heading"><h3 id="cut-heading">Current cut · v{production.revisions.findIndex((r) => r.id === active.id) + 1}</h3><p role="status">{active.cutApproval?.revisionId === active.id ? 'Cut approved for this revision' : 'Next: review and approve this cut or request a revision'}</p>{videos.length > 1 ? <div className="actions" role="group" aria-label="Cuts in this revision">{videos.map((cut, index) => <button className="btn" type="button" key={cut.path} aria-pressed={cut.path === video.path} onClick={() => setSelectedVideo(cut.path)}>Cut {index + 1}</button>)}</div> : null}<video key={videoUrl} className="creation-video" controls preload="metadata" src={videoUrl} aria-label={`Current video revision ${active.id}`} />
        <label htmlFor="cut-feedback">Feedback or change request</label><textarea id="cut-feedback" value={feedback} onChange={(e) => setFeedback(e.target.value)} rows={2} maxLength={2000} />
        <div className="actions"><button type="button" className="btn" disabled={busy} onClick={() => void decide('request-revision')}>Request revision</button><button type="button" className="btn btn-primary" disabled={busy || Boolean(held) || Boolean(active.cutApproval)} onClick={() => void decide('approve-cut')}>{videos.length > 1 ? `Approve all ${videos.length} cuts` : 'Approve this cut'}</button></div>
        <p className="muted">This decision covers all {videos.length} cut{videos.length === 1 ? '' : 's'} in this revision. Publishing package approval, finalization and scheduling are separate.</p>
        <details><summary>Files, transcript and evidence</summary><ul>{active.artifacts.map((artifact) => <li key={artifact.path}><a href={artifactUrl(active.id, artifact.path)} download={artifact.path}>{artifact.path}</a> · {artifact.role}</li>)}</ul>{!active.artifacts.some((a) => a.role === 'transcript' || a.role === 'script') ? <p>No transcript was returned with this cut. Include a transcript.txt artifact on the next return.</p> : null}</details>
        {active.cutApproval && production.project === 'scalargame' ? <p><a className="btn btn-primary" href="#/library">Import finalized publishing package</a></p> : null}
        {active.cutApproval && production.project === 'explainers' ? <p>Download the reviewed files above for local delivery. Required C2/C3/C4 owner approvals and voice/pilot acceptance still apply; this is not publisher approval.</p> : null}
        <details><summary>Revision history and playback</summary><ol>{production.revisions.map((r) => {
          const oldVideos = r.artifacts.filter((a) => a.role === 'video')
          return <li key={r.id}><details><summary>v{production.revisions.findIndex((x) => x.id === r.id) + 1} · {r.id} · {r.cutApproval ? 'cut approved' : 'not approved'}</summary><p>{r.createdAt}</p>{oldVideos.map((cut) => <div key={cut.path}><video className="creation-video" controls preload="none" src={artifactUrl(r.id, cut.path)} aria-label={`Video revision ${r.id}: ${cut.path}`} /><p className="artifact-hash">SHA-256 {cut.sha256}</p></div>)}</details></li>
        })}</ol><p>Production {production.id} · Batch {active.manifest.batchId || 'not assigned'} · Episode {active.manifest.episodeId || 'not assigned'}</p></details>
        {production.project === 'marathon' && active.cutApproval?.revisionId === active.id ? <section className="manual-delivery"><h4>Manual delivery</h4>
          {production.manualDeliveries?.some((d) => d.revisionId === active.id) ? <p>Owner reported delivery on {production.manualDeliveries.find((d) => d.revisionId === active.id)?.reportedAt}. This is not platform confirmation.</p> : <form onSubmit={(e) => void recordDelivery(e)}><label htmlFor="delivery-url">Optional link to your post</label><input id="delivery-url" type="url" value={deliveryUrl} onChange={(e) => setDeliveryUrl(e.target.value)} placeholder="https://…" /><button className="btn" type="submit" disabled={busy}>Record owner-reported delivery</button></form>}
        </section> : null}
      </section> : null}
      <details className="card" open={!active}><summary>Prompt, research and return files</summary><div className="stack">
      <section className="card stack" aria-labelledby="handoff-heading"><h3 id="handoff-heading">Work outside StudioZero</h3><p>Copy this prompt into repo-enabled ChatGPT or Claude Code. Copying does not start work.</p>
        <button type="button" className="btn" onClick={() => void copyPrompt()}>{copied ? 'Copy again' : 'Copy prompt'}</button>
        <details><summary>Prompt text and manual copy</summary><label htmlFor="creation-prompt">Prompt</label><textarea id="creation-prompt" readOnly rows={9} value={prompt} onFocus={(e) => e.currentTarget.select()} /></details>
        <p className="muted">Waiting for files. No agent is connected.</p>
      </section>
      {production.project === 'explainers' ? <section className="card stack" aria-labelledby="research-heading"><h3 id="research-heading">Research decision</h3><p>Do not return a video until the evidence supports the proposed angle.</p>
        <label htmlFor="research-question">Original question</label><textarea id="research-question" value={question} onChange={(e) => setQuestion(e.target.value)} rows={2} />
        <label htmlFor="research-angle">Proposed angle</label><textarea id="research-angle" value={angle} onChange={(e) => setAngle(e.target.value)} rows={2} />
        <label htmlFor="research-sources">Source URLs, one per line</label><textarea id="research-sources" value={sourceText} onChange={(e) => setSourceText(e.target.value)} rows={3} />
        <p>Saved decision: {production.research.status}</p>
        <div className="actions"><button className="btn" type="button" disabled={busy} onClick={() => void research('held')}>Hold topic</button><button className="btn btn-primary" type="button" disabled={busy} onClick={() => void research('accepted')}>Accept research</button></div>
      </section> : null}
      {originals ? <p className="notice notice-warn">Originals is on hold. No artifacts can be imported and no paid work is available.</p> : <form className="card stack" onSubmit={(e) => void importCut(e)} aria-labelledby="return-heading"><h3 id="return-heading">Return a cut to this production</h3>
        <p>Choose a real MP4. A revision manifest binds it to this production; the prior playable revision stays in history.</p>
        <label htmlFor="manifest-file">Returned manifest.json</label><input id="manifest-file" type="file" accept="application/json,.json" onChange={(e) => setManifestFile(e.target.files?.[0] ?? null)} disabled={Boolean(held)} />
        <label htmlFor="cut-files">Files listed in the manifest</label><input id="cut-files" type="file" multiple accept="video/mp4,image/jpeg,image/png,application/json,text/plain" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} disabled={Boolean(held)} />
        <button className="btn btn-primary" type="submit" disabled={busy || !manifestFile || !files.length || Boolean(held)}>{held ? 'Accept research before returning a cut' : busy ? 'Validating…' : 'Validate and review cut'}</button>
      </form>}
      </div></details>
    </> : null}
    {notice ? <p role="status" className="notice">{notice}</p> : null}
    {!production && productions.length ? <section className="card stack"><h3>Saved work</h3><ul>{productions.filter((p) => p.project === project).map((p) => <li key={p.id}><a href={`#/studio/create?project=${encodeURIComponent(project)}&production=${encodeURIComponent(p.id)}`}>{p.title || p.brief.slice(0, 72)} · {p.currentRevisionId ? p.currentRevisionId : 'waiting for files'}</a></li>)}</ul></section> : null}
    {error ? <p ref={errorNotice} tabIndex={-1} className="notice notice-error" role="alert">{error}</p> : null}
  </div>
}
