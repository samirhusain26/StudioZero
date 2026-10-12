import type {
  ActivationResponse,
  Catalog,
  ActivityQuery,
  ActivityResponse,
  ApiError,
  ApproveContentRequest,
  ApproveDraftResponse,
  BatchImportResponse,
  BatchNote,
  BatchNotes,
  CancelJobsRequest,
  DashboardResponse,
  CleanupPreview,
  CleanupResult,
  DeleteEpisodeResponse,
  DraftResponse,
  EditJobRequest,
  EpisodeDetail,
  EpisodeFeedback,
  EpisodeRef,
  ExpectedFileKind,
  FeedbackRequest,
  FileUploadResult,
  HealthResponse,
  HistoryQuery,
  HistoryResponse,
  JobDetailResponse,
  LibraryActionResponse,
  LibraryResponse,
  MarkUsedResponse,
  MetricsStatus,
  NextBatchInfo,
  PauseResponse,
  Problem,
  ScheduleInputs,
  ScheduleResponse,
  UpdateInfo,
  UpdateQueuedResponse,
  WithdrawContentRequest,
} from './types'

// ---------------------------------------------------------------------------
// Passcode: memory only; cleared on any 401. Sessions persist in an HttpOnly cookie.
// ---------------------------------------------------------------------------

export const PASSCODE_KEY = 'scalar-ui-passcode'
let memoryPasscode: string | null = null
const unauthorizedListeners = new Set<() => void>()
let restorePromise: Promise<boolean> | null = null

export function getPasscode(): string | null {
  return memoryPasscode
}

export function setPasscode(value: string): void {
  memoryPasscode = value
  try {
    sessionStorage.removeItem(PASSCODE_KEY)
  } catch {
    // Storage blocked: the passcode lives in memory for this tab only.
  }
}

export function clearPasscode(): void {
  memoryPasscode = null
  try {
    sessionStorage.removeItem(PASSCODE_KEY)
  } catch {
    // ignore
  }
}

/** Reuses one startup restore across React StrictMode's effect replay. */
export function restoreSession(): Promise<boolean> {
  if (!restorePromise) {
    restorePromise = (async () => {
      const existing = await api.session()
      if (existing.authenticated) {
        clearPasscode()
        return true
      }
      let legacy: string | null = null
      try { legacy = sessionStorage.getItem(PASSCODE_KEY) } catch { /* cookie restore still works */ }
      if (!legacy) return false
      try { sessionStorage.removeItem(PASSCODE_KEY) } catch { /* storage may be blocked */ }
      try {
        await api.loginSession(legacy)
        return true
      } finally {
        clearPasscode()
      }
    })()
    const pending = restorePromise
    void pending.finally(() => { if (restorePromise === pending) restorePromise = null }).catch(() => {})
  }
  return restorePromise
}

/** Called after a 401 cleared the passcode (the app returns to the passcode screen). */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ApiRequestError extends Error {
  readonly status: number
  readonly nextAction: string | null
  readonly retryAfterSeconds: number | null
  readonly problems: Problem[]
  /** Machine code from the error body (e.g. `busy`, `not_git`), when the server sent one. */
  readonly code: string | null

  constructor(
    status: number,
    message: string,
    nextAction: string | null,
    retryAfterSeconds: number | null = null,
    problems: Problem[] = [],
    code: string | null = null,
  ) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.nextAction = nextAction
    this.retryAfterSeconds = retryAfterSeconds
    this.problems = problems
    this.code = code
  }
}

/** Retry-After as seconds (delta-seconds or HTTP-date). */
export function parseRetryAfter(value: string | null, now: number = Date.now()): number | null {
  if (!value) return null
  const trimmed = value.trim()
  if (/^\d+$/.test(trimmed)) return Number(trimmed)
  const at = Date.parse(trimmed)
  if (Number.isNaN(at)) return null
  return Math.max(0, Math.ceil((at - now) / 1000))
}

export function waitText(seconds: number): string {
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'}`
  const minutes = Math.ceil(seconds / 60)
  return `${minutes} minute${minutes === 1 ? '' : 's'}`
}

function isApiError(value: unknown): value is ApiError {
  return typeof value === 'object' && value !== null && typeof (value as { error?: unknown }).error === 'string'
}

function errorFrom(status: number, body: unknown, retryAfterHeader: string | null): ApiRequestError {
  const parsed = isApiError(body) ? body : null
  const nextAction = parsed?.nextAction ?? null
  const problems = parsed?.problems ?? []
  if (status === 401) {
    clearPasscode()
    for (const listener of unauthorizedListeners) listener()
    return new ApiRequestError(401, parsed?.error ?? 'The passcode was not accepted.', nextAction ?? 'Enter the passcode again.')
  }
  if (status === 429) {
    const seconds = parseRetryAfter(retryAfterHeader)
    const wait = seconds === null ? 'a while' : waitText(seconds)
    return new ApiRequestError(
      429,
      `Too many attempts. Wait ${wait} before trying again.`,
      nextAction ?? `Try again in ${wait}.`,
      seconds,
    )
  }
  const message = parsed?.error ?? (status >= 500 ? 'The Pi could not complete the request.' : `Request failed (HTTP ${status}).`)
  // The update endpoints answer some conflicts with a machine `code` (possibly without `error`).
  const rawCode = typeof body === 'object' && body !== null ? (body as { code?: unknown }).code : undefined
  return new ApiRequestError(status, message, nextAction, null, problems, typeof rawCode === 'string' ? rawCode : null)
}

const MUTATING = new Set(['POST', 'PUT', 'DELETE', 'PATCH'])

/** Headers every /api request carries. */
export function apiHeaders(method: string, extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'application/json', ...extra }
  const passcode = getPasscode()
  if (passcode) headers.Authorization = `Bearer ${passcode}`
  if (MUTATING.has(method.toUpperCase())) headers['X-Scalar-Request'] = '1'
  return headers
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

export type Query = Record<string, string | number | undefined | null>

export function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const text = params.toString()
  return text ? `${path}?${text}` : path
}

interface RequestOptions {
  json?: unknown
  /** Raw body with explicit content type (e.g. batch.json bytes). */
  raw?: { body: BodyInit; contentType: string }
  query?: Query
  signal?: AbortSignal
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const extra: Record<string, string> = {}
  let body: BodyInit | null = null
  if (options.json !== undefined) {
    extra['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  } else if (options.raw) {
    extra['Content-Type'] = options.raw.contentType
    body = options.raw.body
  }
  const init: RequestInit = {
    method,
    headers: apiHeaders(method, extra),
    credentials: 'same-origin',
    cache: 'no-store',
    body,
  }
  if (options.signal) init.signal = options.signal
  let response: Response
  try {
    response = await fetch(withQuery(path, options.query), init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiRequestError(0, 'The Pi could not be reached.', 'Check the tailnet connection, then try again.')
  }
  const data = await readBody(response)
  if (!response.ok) throw errorFrom(response.status, data, response.headers.get('Retry-After'))
  return data as T
}

/** Authenticated download (fetch → blob → save), for CSV/JSON exports and backups. */
export async function download(path: string, fallbackName: string, query?: Query): Promise<string> {
  let response: Response
  try {
    response = await fetch(withQuery(path, query), { headers: apiHeaders('GET', { Accept: '*/*' }), cache: 'no-store', credentials: 'same-origin' })
  } catch {
    throw new ApiRequestError(0, 'The Pi could not be reached.', 'Check the tailnet connection, then try again.')
  }
  if (!response.ok) throw errorFrom(response.status, await readBody(response), response.headers.get('Retry-After'))
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  const name = match?.[1] ? decodeURIComponent(match[1]) : fallbackName
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
  return name
}

// ---------------------------------------------------------------------------
// Uploads with progress (XMLHttpRequest)
// ---------------------------------------------------------------------------

export interface UploadProgress {
  loaded: number
  total: number
}

export interface UploadHandle<T> {
  promise: Promise<T>
  abort: () => void
}

export type UploadContentType = 'video/mp4' | 'image/jpeg'

export function upload<T>(
  method: 'PUT' | 'POST',
  path: string,
  file: Blob,
  contentType: UploadContentType,
  onProgress?: (progress: UploadProgress) => void,
): UploadHandle<T> {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open(method, path)
    for (const [name, value] of Object.entries(apiHeaders(method, { 'Content-Type': contentType }))) {
      xhr.setRequestHeader(name, value)
    }
    xhr.responseType = 'text'
    xhr.upload.onprogress = (event: ProgressEvent) => {
      onProgress?.({ loaded: event.loaded, total: event.lengthComputable ? event.total : file.size })
    }
    xhr.onload = () => {
      let data: unknown = null
      try {
        data = xhr.responseText ? (JSON.parse(xhr.responseText) as unknown) : null
      } catch {
        data = null
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T)
      else reject(errorFrom(xhr.status, data, xhr.getResponseHeader('Retry-After')))
    }
    xhr.onerror = () => reject(new ApiRequestError(0, 'Upload interrupted.', 'Select the file again to retry.'))
    xhr.onabort = () => reject(new ApiRequestError(0, 'Upload cancelled.', 'Select the file again to retry.'))
    xhr.send(file)
  })
  return { promise, abort: () => xhr.abort() }
}

// ---------------------------------------------------------------------------
// Typed endpoints
// ---------------------------------------------------------------------------

const enc = encodeURIComponent

export const api = {
  session: () => request<{ authenticated: boolean }>('GET', '/api/session'),
  loginSession: (passcode: string) => {
    setPasscode(passcode)
    return request<{ authenticated: boolean }>('POST', '/api/session', { json: {} })
  },
  logoutSession: () => request<{ authenticated: boolean }>('DELETE', '/api/session'),
  health: () => request<HealthResponse>('GET', '/api/health'),
  catalog: () => request<Catalog>('GET', '/api/catalog'),
  dashboard: (signal?: AbortSignal) => request<DashboardResponse>('GET', '/api/dashboard', signal ? { signal } : {}),
  pause: (note?: string) => request<PauseResponse>('POST', '/api/pause', { json: note ? { note } : {} }),

  library: () => request<LibraryResponse>('GET', '/api/library'),
  importBatch: (batchJson: string) =>
    request<BatchImportResponse>('POST', '/api/library/batches', { raw: { body: batchJson, contentType: 'application/json' } }),
  uploadBatchFile: (batchId: string, kind: ExpectedFileKind, name: string, file: Blob, onProgress?: (p: UploadProgress) => void) =>
    upload<FileUploadResult>(
      'PUT',
      `/api/library/batches/${enc(batchId)}/files/${kind === 'video' ? 'videos' : 'covers'}/${enc(name)}`,
      file,
      kind === 'video' ? 'video/mp4' : 'image/jpeg',
      onProgress,
    ),
  approveContent: (body: ApproveContentRequest) => request<LibraryActionResponse>('POST', '/api/library/approve', { json: body }),
  withdrawContent: (body: WithdrawContentRequest) => request<LibraryActionResponse>('POST', '/api/library/withdraw', { json: body }),
  deleteEpisode: (episodeId: string, revision: number) =>
    request<DeleteEpisodeResponse>('DELETE', `/api/library/episodes/${enc(episodeId)}/${revision}`),
  cleanupPreview: () => request<CleanupPreview>('GET', '/api/library/cleanup'),
  removePostedVideos: (videoSha256: string[]) => request<CleanupResult>('POST', '/api/library/cleanup', { json: { videoSha256 } }),

  schedule: () => request<ScheduleResponse>('GET', '/api/schedule'),
  createDraft: (inputs: ScheduleInputs) => request<DraftResponse>('POST', '/api/schedule/drafts', { json: inputs }),
  getDraft: (sha: string) => request<DraftResponse>('GET', `/api/schedule/drafts/${enc(sha)}`),
  approveDraft: (sha: string, confirmation: string) =>
    request<ApproveDraftResponse>('POST', `/api/schedule/drafts/${enc(sha)}/approve`, { json: { confirmation } }),
  cancelJobs: (body: CancelJobsRequest) => request<DraftResponse>('POST', '/api/schedule/cancel', { json: body }),
  editJob: (body: EditJobRequest) => request<DraftResponse>('POST', '/api/schedule/edit', { json: body }),

  history: (query: HistoryQuery) => request<HistoryResponse>('GET', '/api/history', { query: { ...query, format: 'json' } }),
  exportHistory: (query: HistoryQuery, format: 'json' | 'csv') =>
    download('/api/history', `scalar-history.${format}`, { ...query, format, limit: query.limit ?? 1000 }),
  job: (id: string) => request<JobDetailResponse>('GET', `/api/jobs/${enc(id)}`),
  activity: (query: ActivityQuery, signal?: AbortSignal) =>
    request<ActivityResponse>('GET', '/api/activity', { query: { ...query, format: 'json' }, ...(signal ? { signal } : {}) }),
  exportActivity: (query: ActivityQuery, format: 'json' | 'csv') =>
    download('/api/activity', `scalar-activity.${format}`, { ...query, format, limit: query.limit ?? 500 }),

  activation: () => request<ActivationResponse>('GET', '/api/activation'),
  backup: () => download('/api/backup', 'scalar-social-backup.tar.gz'),

  // Pi self-update (REBUILD_CONTRACTS.md §1). The UI never fetches from GitHub itself.
  updateStatus: (signal?: AbortSignal) => request<UpdateInfo>('GET', '/api/system/update/status', signal ? { signal } : {}),
  updateCheck: () => request<UpdateQueuedResponse>('POST', '/api/system/update/check', { json: {} }),
  /** `confirm` must be exactly `UPDATE TO <40-hex sha>`. */
  updateStart: (sha: string) => request<UpdateQueuedResponse>('POST', '/api/system/update/start', { json: { confirm: `UPDATE TO ${sha}` } }),

  // Episode detail, feedback, batch notes, next batch (REBUILD_CONTRACTS.md §2).
  episodeDetail: (episodeId: string, revision: number) =>
    request<EpisodeDetail>('GET', `/api/library/episodes/${enc(episodeId)}/${revision}`),
  saveFeedback: (episodeId: string, revision: number, body: FeedbackRequest) =>
    request<EpisodeFeedback>('PUT', `/api/library/episodes/${enc(episodeId)}/${revision}/feedback`, { json: body }),
  clearFeedback: (episodeId: string, revision: number) =>
    request<null>('DELETE', `/api/library/episodes/${enc(episodeId)}/${revision}/feedback`),
  markFeedbackUsed: (items: EpisodeRef[]) => request<MarkUsedResponse>('POST', '/api/feedback/mark-used', { json: { items } }),
  batchNotes: (batchId: string) => request<BatchNotes>('GET', `/api/library/batches/${enc(batchId)}/notes`),
  saveBatchNote: (batchId: string, kind: 'brief' | 'retro', text: string) =>
    request<BatchNote>('PUT', `/api/library/batches/${enc(batchId)}/notes/${kind}`, { json: { text } }),
  nextBatch: () => request<NextBatchInfo>('GET', '/api/next-batch'),

  // Post stats controls. The UI only writes request/flag files; scalar-social-metrics.{timer,path} do the reads.
  getMetricsStatus: () => request<MetricsStatus>('GET', '/api/metrics/status'),
  setMetricsEnabled: (enabled: boolean) => request<MetricsStatus>('PUT', '/api/metrics/enabled', { json: { enabled } }),
  /** 409 while a read is already pending; 422 for a backfill outside 0–93. */
  requestMetricsRead: (backfill?: number) =>
    request<MetricsStatus>('POST', '/api/metrics/read', { json: backfill === undefined ? {} : { backfill } }),
}
