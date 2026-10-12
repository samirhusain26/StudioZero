/**
 * Scalar Pi publishing UI — HTTP API contract.
 *
 * This file is the single source of truth for every request and response shape
 * exchanged between the React frontend (publisher/ui) and the stdlib Python backend
 * (publisher/app/ui_server.py + ui_*.py). The backend is implemented to match it.
 *
 * Conventions
 * - All bodies are JSON (UTF-8) unless stated otherwise. Field names are camelCase.
 * - Timestamps (`IsoUtc`) are ISO-8601 in UTC: `2026-10-12T13:00:00Z` or `…+00:00`.
 *   The frontend renders them in a named IANA zone plus UTC; the backend never
 *   pre-formats wall-clock text except inside `label`/`detail` strings.
 * - Local timestamps (`IsoOffset`) carry their offset: `2026-10-12T09:00:00-04:00`.
 * - Dates (`IsoDate`) are `YYYY-MM-DD`.
 * - Hashes (`Sha256`) are 64 lowercase hex characters.
 * - Platform order everywhere: instagram, facebook, threads, x, youtube, bluesky, tiktok.
 * - Every `/api/*` request except `GET /api/health` carries `Authorization: Bearer <passcode>`.
 *   POST/PUT/DELETE additionally carry `X-Scalar-Request: 1` (and the browser's `Origin`).
 * - Media GETs (`/api/media/...`) use the tokenized URLs returned in responses
 *   (`?t=<exp>.<hex>`, valid ~1 h) and need no Authorization header.
 * - Every error response has status ≥ 400 and body `ApiError`.
 *   401 = passcode missing/wrong; 429 = per-client backoff with `Retry-After` (seconds);
 *   409 = conflict (pending approval, dispatched job, publisher busy); 422 = validation.
 */

// ---------------------------------------------------------------------------
// Shared vocabulary (mirrors contract/library_contract.py)
// ---------------------------------------------------------------------------

/** All publishing platforms, in canonical display order. */
export const PLATFORMS = ['instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok'] as const
export type Platform = (typeof PLATFORMS)[number]

/** Platforms with a caption in `publication.captions` (YouTube uses `publication.youtube`). */
export const CAPTION_PLATFORMS = ['instagram', 'facebook', 'threads', 'x', 'bluesky', 'tiktok'] as const
export type CaptionPlatform = (typeof CAPTION_PLATFORMS)[number]

/** Platforms whose post text renders clickable links; `{link}` is refused elsewhere. */
export const LINK_PLATFORMS = ['facebook', 'threads', 'x', 'bluesky'] as const
export type LinkPlatform = (typeof LINK_PLATFORMS)[number]

/** Platforms with an own first comment / reply route (`publication.firstComment`). */
export const COMMENT_PLATFORMS = ['instagram', 'threads', 'bluesky', 'x'] as const
export type CommentPlatform = (typeof COMMENT_PLATFORMS)[number]

/** Platforms that can carry a delayed answer reply (`publication.answerReply`). */
export const ANSWER_REPLY_PLATFORMS = ['instagram', 'threads', 'bluesky'] as const
export type AnswerReplyPlatform = (typeof ANSWER_REPLY_PLATFORMS)[number]

/** A game id from the catalog (`GET /api/catalog`, projects[].games[].id); Scalargame's four today. */
export type Game = string

/** A format id from the catalog (projects[].formats[].id). */
export type Format = string

export const DIFFICULTIES = ['approachable', 'moderate', 'challenging'] as const
export type Difficulty = (typeof DIFFICULTIES)[number]

/** `YYYY-MM-DD`. */
export type IsoDate = string
/** UTC ISO-8601 timestamp, e.g. `2026-10-12T13:00:00Z`. */
export type IsoUtc = string
/** ISO-8601 with a numeric offset, e.g. `2026-10-12T09:00:00-04:00`. */
export type IsoOffset = string
/** 64 lowercase hex characters. */
export type Sha256 = string
/** Same-origin URL with a short-lived media token: `/api/media/videos/<sha>.mp4?t=<exp>.<hex>`. */
export type MediaUrl = string
/** IANA zone name, e.g. `America/New_York`. */
export type TimeZoneName = string

/** Channel route in /etc/scalar-social/config.json `channels.<platform>.route`. */
export type ChannelRoute = 'buffer' | 'instagram' | 'facebook' | 'threads' | 'bluesky' | 'disabled'

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** Body of every non-2xx response. Texts are plain language, never vendor bodies or secrets. */
export interface ApiError {
  /** What went wrong, e.g. "That passcode was not accepted." */
  error: string
  /** A safe thing the owner can do next, or null when there is nothing to do. */
  nextAction: string | null
  /** 422 only: contract validation problems (library_contract.Report items). */
  problems?: Problem[]
  /** Machine code for some conflicts, e.g. `busy`, `not_git`, `stale_check` (update endpoints). */
  code?: string
}

/** A validation item from `library_contract.Report` (errors and warnings share the shape). */
export interface Problem {
  /** Machine code, e.g. `spoiler`, `length`, `hash`, `media`, `dirty_generator`. */
  code: string
  /** JSON path inside batch.json / the episode, e.g. `episodes[0].publication.captions.x`. */
  path: string
  /** Plain-language message. */
  message: string
}

/** Ledger error categories (runner.py + ui_health.ERRORS). */
export type ErrorCategory =
  | 'authorization'
  | 'rejected'
  | 'budget'
  | 'media'
  | 'rate_limit'
  | 'uncertain_response'
  | 'remote_confirmation_pending'
  | 'missed_slot'
  | 'retry_limit'
  | 'remote_rejected'
  | 'parent_unavailable'
  | 'cancelled'

/** `ui_health.ERRORS[category]` rendered for one job or issue. */
export interface PlainError {
  category: ErrorCategory
  /** Short title, e.g. "Platform rejected the post". */
  title: string
  /** One or two plain sentences. */
  detail: string
  /** Safe next action. Never "post again" for uncertain/accepted/dispatching jobs. */
  nextAction: string | null
}

// ---------------------------------------------------------------------------
// GET /api/health  (open, no auth)
// ---------------------------------------------------------------------------

/** Per-client backoff after failed passcode attempts (5 free, then 2^(n-5) s, max 900 s). */
export interface BackoffState {
  /** True while this client must wait before the next passcode attempt. */
  locked: boolean
  /** Seconds until the next attempt is accepted; null when not locked. */
  retryAfterSeconds: number | null
  /** Consecutive failed attempts recorded for this client. */
  failures: number
}

export interface HealthResponse {
  ok: true
  /** Backend version string, e.g. `ui-2026.10.06`. */
  version: string
  /** Backoff state for the calling client (as identified by the server). */
  backoff: BackoffState
}

// ---------------------------------------------------------------------------
// GET /api/dashboard
// ---------------------------------------------------------------------------

/** Three-valued fact; `unknown` when evidence is missing or unreadable. */
export type TriState = 'yes' | 'no' | 'unknown'

/** "Posting test passed" for one platform (first posting-test receipts). */
export interface PostingTestStatus {
  state: TriState
  /** Plain label, e.g. "Passed", "Not run", "Failed". Always shown next to any colour. */
  label: string
  /** When the receipt was recorded. */
  passedAt: IsoUtc | null
  /** Public permalink of the test post, when confirmed. */
  permalink: string | null
  detail: string | null
}

/** "Currently authenticated" for one platform (token health, renewal markers, deadlines). */
export interface AuthStatus {
  state: TriState
  /** e.g. "Authenticated", "Renewal failed", "No token", "Not applicable (Buffer)". */
  label: string
  /** When the token health was last checked. */
  checkedAt: IsoUtc | null
  /** Token expiry or data-access deadline (e.g. Facebook), if known. */
  expiresAt: IsoUtc | null
  /** True when a renewal failure marker exists. */
  renewalFailed: boolean
  detail: string | null
}

/** "Recurring publishing enabled" for one platform (config channel flags). */
export interface RecurringPlatformStatus {
  state: TriState
  /** e.g. "Enabled", "Disabled", "Disabled: route blocked". */
  label: string
  channelEnabled: boolean
  route: ChannelRoute
  identityVerified: boolean
  publishingVerified: boolean
  /** config.channels.<p>.reason or a plain explanation. */
  detail: string | null
}

/** The three statuses. They are separate facts and are never merged into one indicator. */
export interface DashboardStatuses {
  postingTestPassed: { platforms: Record<Platform, PostingTestStatus> }
  currentlyAuthenticated: { platforms: Record<Platform, AuthStatus> }
  recurringEnabled: {
    /** Overall: yes only if config unpaused AND no PAUSED sentinel AND publisher timer enabled. */
    state: TriState
    label: string
    configPaused: boolean
    /** STATE/PAUSED exists. */
    pausedSentinel: boolean
    publisherTimerEnabled: boolean
    publisherTimerActive: boolean
    platforms: Record<Platform, RecurringPlatformStatus>
  }
}

export type TimerRole = 'publisher' | 'monitor' | 'renewal' | 'metrics'

/** One systemd timer, from `systemctl show` (no journal access). */
export interface TimerStatus {
  /** Unit name, e.g. `scalar-social.timer`. */
  unit: string
  role: TimerRole
  /** Plain name, e.g. "Publisher", "Monitor", "Instagram token renewal". */
  label: string
  enabled: boolean
  active: boolean
  lastRunAt: IsoUtc | null
  /** Result of the service's last run. */
  lastResult: 'success' | 'failed' | 'never' | 'unknown'
  /** Plain text for the last result, e.g. "exit-code" mapped to words. */
  lastResultDetail: string | null
  nextRunAt: IsoUtc | null
}

/** Age of a status file written by another process. */
export interface Freshness {
  updatedAt: IsoUtc | null
  ageSeconds: number | null
  /** Threshold used to call it fresh. */
  maxAgeSeconds: number
  fresh: boolean
  /** e.g. "Updated 4 min ago", "Missing". */
  label: string
  /** Overall ok flag inside the file (health.json `ok`), when present. */
  ok: boolean | null
}

/** A counted budget with a rolling window. */
export interface Budget {
  used: number
  limit: number
  remaining: number
  /** Plain window, e.g. "last 31 days", "last 24 hours". */
  window: string
  /** e.g. "7 of 120 deployments used". */
  label: string
  /** True when remaining is below the warning margin. */
  low: boolean
}

export interface StorageStatus {
  freeBytes: number
  totalBytes: number
  /** Uploads are refused when free space < upload size + reserve (2 GB). */
  reserveBytes: number
  low: boolean
  label: string
}

export type IssueSeverity = 'error' | 'warning' | 'info'

/** A plain-language problem with a safe next action. */
export interface Issue {
  /** Stable id for React keys, e.g. `job:<id>` or `monitor-stale`. */
  id: string
  severity: IssueSeverity
  /** Ledger category when applicable, else a short code such as `config-permissions`. */
  category: ErrorCategory | string
  title: string
  detail: string
  nextAction: string | null
  platform: Platform | null
  jobId: string | null
  at: IsoUtc | null
}

/** Ledger job states (runner.py). */
export type LedgerStatus =
  | 'ready'
  | 'dispatching'
  | 'accepted'
  | 'uncertain'
  | 'confirmed'
  | 'failed'
  | 'expired'
  | 'blocked'

/** States that must never offer "post again". */
export type UnresolvedStatus = 'dispatching' | 'accepted' | 'uncertain'

/** Reconciliation facts for an unresolved job. */
export interface Reconciliation {
  state: UnresolvedStatus
  /** Plain label, e.g. "Waiting for the platform to confirm". */
  label: string
  lastCheckAt: IsoUtc | null
  nextCheckAt: IsoUtc | null
  /**
   * Documented owner actions, e.g. "Check the profile for this post",
   * "If it is there, mark it resolved with evidence: sudo …". Never "post again".
   */
  ownerActions: string[]
}

/** A job awaiting reconciliation; shown on the dashboard with no repost/retry control. */
export interface UncertainJob {
  jobId: string
  platform: Platform
  accountId: string
  slotUtc: IsoUtc
  /** Ledger episode key, e.g. `scalar:BOL:clues` or `scalar:BOL:clues#comment`. */
  episode: string
  status: UnresolvedStatus
  dispatchedAt: IsoUtc | null
  error: PlainError | null
  reconciliation: Reconciliation
}

/** Pending approval request (STATE/approval/request.json). */
export interface ApprovalRequestState {
  draftSha256: Sha256
  requestedAt: IsoUtc
}

/** Last applier/bind result (STATE/approval/result.json). */
export type ApprovalResult =
  | {
      status: 'manifest-ready'
      draftSha256: Sha256
      manifestSha256: Sha256
      jobs: number
      deployment: DeploymentInfo
      at: IsoUtc
    }
  | {
      /** Root bind step wrote approval.manifestSha256/approvedAt into config. */
      status: 'bound'
      draftSha256: Sha256
      manifestSha256: Sha256
      jobs: number
      at: IsoUtc
    }
  | {
      /** Staging/demo mode: validated only, no deploy, no manifest, no config change. */
      status: 'validated-no-deploy'
      draftSha256: Sha256
      at: IsoUtc
    }
  | {
      status: 'failed'
      draftSha256: Sha256 | null
      /** e.g. `validation`, `deploy`, `verification`, `dispatched-changed`, `scope`. */
      category: string
      /** Plain reason. */
      message: string
      at: IsoUtc
    }

export interface DeploymentInfo {
  /** Pages deployment id, when deployed. */
  id: string | null
  url: string | null
  /** Media files verified by public hash. */
  verified: number
  files: number
}

/** Approval binding as seen by the UI (config.approval + manifests dir). */
export interface ApprovalState {
  manifestSha256: Sha256 | null
  approvedAt: IsoUtc | null
  /** config.approval.manifestSha256 equals manifests/approved.json hash. */
  bound: boolean
  scope: Platform[]
  pendingRequest: ApprovalRequestState | null
  lastResult: ApprovalResult | null
}

export interface DashboardResponse {
  generatedAt: IsoUtc
  /** Publishing zone from config (used for local-time display). */
  displayTimezone: TimeZoneName
  /** Publishing is paused (config.paused OR PAUSED sentinel). */
  paused: boolean
  statuses: DashboardStatuses
  timers: TimerStatus[]
  freshness: {
    /** STATE/health.json written by the runner. */
    healthJson: Freshness
    /** Monitor's last successful check. */
    monitor: Freshness
  }
  budgets: {
    /** Cloudflare Pages deployments, 120 per 31 days. */
    pages: Budget
    /** Buffer API calls, local cap 200 per 24 hours. */
    buffer: Budget
  }
  storage: StorageStatus
  issues: Issue[]
  approval: ApprovalState
  uncertainJobs: UncertainJob[]
  /** "Where things stand" summary (REBUILD_CONTRACTS.md §2). */
  standing: Standing
}

// ---------------------------------------------------------------------------
// POST /api/pause   body: PauseRequest
// ---------------------------------------------------------------------------

export interface PauseRequest {
  /** Optional plain note recorded in the event log. */
  note?: string
}

export interface PauseResponse {
  paused: true
  /** True when PAUSED already existed. */
  alreadyPaused: boolean
  at: IsoUtc
}

// ---------------------------------------------------------------------------
// Library — batch.json episode (contract v1 and v2, BATCH_CONTRACT.md)
// ---------------------------------------------------------------------------

export interface Choice {
  key: 'A' | 'B' | 'C' | 'D'
  label: string
}

export interface Creative {
  hook: string
  question: string
  clues: string[]
  /** 2–4 choices or null. */
  choices: Choice[] | null
  answer: string
  answerAliases: string[]
  explanation: string
}

export interface EvidenceSource {
  title: string
  /** HTTPS URL. */
  url: string
  retrieved: IsoDate
}

export interface Evidence {
  sources: EvidenceSource[]
  checks: { uniqueAnswer: boolean; [key: string]: unknown }
  reviewer: string
}

export interface Poll {
  question: string
  /** 2–4 options of 1–25 characters, containing the answer exactly once. */
  options: string[]
}

export interface AnswerReply {
  /** Must open with a spacer line; the only field allowed to contain the answer. */
  text: string
  /** 0.25–168 hours after the parent post. */
  delayHours: number
}

export interface YoutubeText {
  /** ≤ 100 characters, no `<` or `>`. */
  title: string
  /** ≤ 5000 UTF-8 bytes, no `<` or `>`. */
  description: string
}

export interface Publication {
  /** Site path such as `/scalar`. */
  deepLink: string
  /** `[a-z0-9_]{1,64}`. */
  utmCampaign: string
  /** Caption per platform; `{link}` only on LINK_PLATFORMS; null/absent = none. */
  captions: Partial<Record<CaptionPlatform, string | null>>
  youtube: YoutubeText | null
  altText: string
  hashtags: string[]
  credits: string[]
  poll: Poll | null
  firstComment: Partial<Record<CommentPlatform, string | null>> | null
  answerReply: AnswerReply | null
}

export type EligibilityStatus = 'qa-passed' | 'approved' | 'withdrawn' | 'expired'

export interface EpisodeEligibility {
  status: EligibilityStatus
  notBefore: IsoDate | null
  reviewBy: IsoDate | null
  expiresAt: IsoDate | null
}

/** One episode exactly as in batch.json (schemaVersion 1). Immutable once imported. */
export interface ContractEpisode {
  episodeId: string
  questionId: string
  revision: number
  game: Game
  format: Format
  language: string
  difficulty: Difficulty
  styleId: string
  experimentId: string | null
  variantId: string | null
  creative: Creative
  evidence: Evidence
  music: { trackId: string; sha256: Sha256; license: string } | null
  video: {
    file: string
    sha256: Sha256
    bytes: number
    durationSeconds: number
    width: number
    height: number
    fps: string
    videoCodec: 'h264'
    audioCodec: 'aac' | null
  }
  cover: { file: string; sha256: Sha256; bytes: number }
  publication: Publication
  eligibility: EpisodeEligibility
}

export type CreditLicense =
  | 'CC0-1.0' | 'CC-BY-4.0' | 'CC-BY-SA-4.0' | 'OFL-1.1' | 'Pexels' | 'Pixabay' | 'TMDB' | 'Wikipedia-CC-BY-SA' | 'owner' | 'generated' | 'public-domain'

export interface Credit {
  kind: string
  title: string
  creator: string | null
  sourceUrl: string | null
  /** v1 credits (normalized on the Pi) carry the v1 licence text or null. */
  license: CreditLicense | string | null
  attribution: string | null
  sha256: Sha256 | null
}

export interface Disclosure {
  aiGenerated: boolean
  aiKinds: string[]
  realisticSynthetic: boolean
  note: string
}

export type Engine = 'motion' | 'story'
/** Who rendered a motion episode: the Mac's render.sh or the Studio's browser export (null: not recorded). */
export type Renderer = 'render.sh' | 'web'

/** One episode exactly as in a contract v2 batch.json. projectData is checked by the project's module. */
export interface ContractEpisodeV2 {
  episodeId: string
  contentId: string
  revision: number
  format: Format
  language: string
  render: { engine: Engine; route: 'recap' | 'series' | null; renderer: Renderer | null; kitVersion: string; renderSha256: Sha256; models: { role: string; id: string }[]; costUsd: number }
  experimentId: string | null
  variantId: string | null
  tags: string[]
  video: ContractEpisode['video']
  cover: ContractEpisode['cover']
  link: { url: string; utmCampaign: string } | null
  publication: Omit<Publication, 'deepLink' | 'utmCampaign' | 'credits'>
  credits: Credit[]
  disclosure: Disclosure
  eligibility: EpisodeEligibility
  projectData: Record<string, unknown>
}

/** batch.json top level (the UI only reads batchId/episodes before POSTing raw bytes). */
export interface BatchDocument {
  schemaVersion: 1
  batchId: string
  createdAt: IsoUtc
  generator: { repoCommit: string; dirty: boolean; assetKitVersion: string }
  sourceSnapshotHash: Sha256
  styleRecipes: { styleId: string; game: Game; version: number; summary: string }[]
  episodes: ContractEpisode[]
}

// ---------------------------------------------------------------------------
// GET /api/library
// ---------------------------------------------------------------------------

/** `manual` = an older phone upload (that route is removed; its batches stay readable). */
export type BatchOrigin = 'mac' | 'manual' | 'legacy'

/** Library index episode status (index.sqlite3 episodes.status). */
export type EpisodeStatus = 'awaiting_files' | 'reviewable' | 'approved' | 'withdrawn' | 'expired' | 'invalid'

/** Media facts re-measured by ffprobe on the Pi (library_contract.measure). */
export interface MeasuredMedia {
  bytes: number
  durationSeconds: number | null
  width: number | null
  height: number | null
  /** Rational, e.g. `30/1`. */
  fps: string | null
  videoCodec: string | null
  pixFmt: string | null
  videoStreams: number
  audioStreams: number
  /** null when silent. */
  audioCodec: string | null
  audioSampleRate: number | null
  audioChannels: number | null
  /** moov before mdat; null if not checked. */
  fastStart: boolean | null
}

/** Per-platform media eligibility (library_contract.platform_eligibility). */
export interface PlatformEligibility {
  eligible: boolean
  /** Plain reason when not eligible. */
  reason: string | null
}

/** One content approval/withdrawal record (approval of record, L2). */
export interface ApprovalRecord {
  id: number
  action: 'approve' | 'withdraw'
  reviewer: string
  at: IsoUtc
  videoSha256: Sha256
  coverSha256: Sha256 | null
  metadataSha256: Sha256
  captionSha256: Sha256
  note: string | null
}

/** Where this episode's questionId already posted (ledger, incl. previousAccountIds). */
export interface PostedRecord {
  platform: Platform
  accountId: string
  /** Ledger status of that row. */
  status: LedgerStatus
  slotUtc: IsoUtc
}

export interface LibraryBatch {
  batchId: string
  origin: BatchOrigin
  /** batch.json createdAt (null for legacy/manual where unknown). */
  createdAt: IsoUtc | null
  importedAt: IsoUtc
  batchJsonSha256: Sha256
  /** batch.json generator.dirty === true (shown as a warning). */
  generatorDirty: boolean
  repoCommit: string | null
  /** Import warnings (Problem list). */
  warnings: Problem[]
  episodeCount: number
  /** Episodes still waiting for a video/cover upload. */
  awaitingFiles: number
}

export interface LibraryEpisode {
  episodeId: string
  revision: number
  batchId: string
  questionId: string
  game: Game
  format: Format | null
  difficulty: Difficulty | null
  status: EpisodeStatus
  /** Plain label for the status, e.g. "Awaiting files", "Ready for review". */
  statusLabel: string
  metadataSha256: Sha256
  videoSha256: Sha256
  coverSha256: Sha256 | null
  /** Tokenized playback URL; null while the video is not on the Pi. */
  videoUrl: MediaUrl | null
  /** Tokenized cover URL; null while the cover is not on the Pi. */
  coverUrl: MediaUrl | null
  /** null while the video is not on the Pi. */
  media: MeasuredMedia | null
  /** When the posted video was removed from the Pi to free space (cover and record kept); re-uploading restores it. */
  videoRemovedAt: IsoUtc | null
  platforms: Record<Platform, PlatformEligibility>
  /** Validation problems (errors) for this episode. */
  problems: Problem[]
  approvals: ApprovalRecord[]
  /** The approval that matches current hashes, if any. */
  currentApproval: ApprovalRecord | null
  /** Ever referenced by an approved manifest (L11: then read-only, never deletable). */
  inManifest: boolean
  /** True only when never in an approved manifest and the server allows deletion. */
  deletable: boolean
  /** Video registered in place from legacy site/ media. */
  legacy: boolean
  /** Other episodes sharing this questionId (variants), as `episodeId@revision`. */
  variants: string[]
  /** Accounts where this questionId already posted. */
  postedOn: PostedRecord[]
  /** Full contract metadata (captions, creative, eligibility dates); read it with lib/episodeView.readEpisode. */
  episode: ContractEpisode | ContractEpisodeV2
  /** Contract version of the batch the episode came from. */
  schemaVersion: 1 | 2
  /** Project (v1 episodes are Scalargame's). */
  project: string
  engine: Engine
  route: 'recap' | 'series' | null
  /** null: not recorded (every v1 episode). */
  renderer: Renderer | null
  models: { role: string; id: string }[]
  /** Paid-API spend for this episode; null for v1. */
  costUsd: number | null
  credits: Credit[]
  /** null: not declared (v1). */
  disclosure: Disclosure | null
  tags: string[]
}

export interface LibraryResponse {
  generatedAt: IsoUtc
  /** Publishing zone from config (used for local-time display). */
  displayTimezone: TimeZoneName
  batches: LibraryBatch[]
  /** Sorted by (batchId, episodeId, revision). */
  episodes: LibraryEpisode[]
}

// ---------------------------------------------------------------------------
// POST /api/library/batches   body: raw batch.json bytes (Content-Type application/json, ≤ 1 MB)
// ---------------------------------------------------------------------------

export type ExpectedFileKind = 'video' | 'cover'

/** One file the batch expects, with whether the Pi already holds verified bytes. */
export interface ExpectedFile {
  /** Relative path as in batch.json, e.g. `videos/scalar-clues-001.mp4`. */
  file: string
  /** Bare name the owner selects, e.g. `scalar-clues-001.mp4`. */
  name: string
  kind: ExpectedFileKind
  episodeId: string
  revision: number
  sha256: Sha256
  bytes: number
  /** Verified bytes with this hash are already on the Pi; the upload is skipped. */
  present: boolean
}

export interface BatchImportResponse {
  batchId: string
  origin: BatchOrigin
  /** False when the same batch.json was already imported (merge no-op). */
  created: boolean
  /** Per-episode merge outcome (BATCH_CONTRACT.md merge table). */
  merge: {
    episodeId: string
    revision: number
    outcome: 'added' | 'new-revision' | 'already-imported' | 'rejected'
    message: string | null
  }[]
  expected: ExpectedFile[]
  /** Blocking validation errors (empty when accepted). */
  problems: Problem[]
  /** Non-blocking warnings, e.g. dirty generator. */
  warnings: Problem[]
}

// ---------------------------------------------------------------------------
// PUT /api/library/batches/<batchId>/files/<videos|covers>/<name>
//   body: file bytes; Content-Type video/mp4 or image/jpeg; Content-Length required
// ---------------------------------------------------------------------------

export interface FileUploadResult {
  /** e.g. `videos/scalar-clues-001.mp4`. */
  file: string
  kind: ExpectedFileKind
  episodeId: string
  /** Hash and size computed while streaming. */
  sha256: Sha256
  bytes: number
  expectedSha256: Sha256
  expectedBytes: number
  /** sha256 and size both equal the batch.json declaration. */
  matched: boolean
  /** `stored` = new verified bytes; `already-present` = same hash existed; `rejected` = not stored. */
  outcome: 'stored' | 'already-present' | 'rejected'
  /** Plain reason when rejected or problems found. */
  message: string | null
  /** Media/validation problems for this file. */
  problems: Problem[]
  /** Episode status after this upload. */
  episodeStatus: EpisodeStatus
}

// ---------------------------------------------------------------------------
// POST /api/library/approve    body: ApproveContentRequest
// POST /api/library/withdraw   body: WithdrawContentRequest
// ---------------------------------------------------------------------------

export interface EpisodeRef {
  episodeId: string
  revision: number
}

export interface ApproveContentRequest {
  items: EpisodeRef[]
  /** Reviewer name recorded with the approval of record. */
  reviewer: string
}

export interface WithdrawContentRequest {
  items: EpisodeRef[]
  reviewer: string
  note?: string
}

/** Per-item outcome; the request succeeds (200) even when some items are refused. */
export interface LibraryActionResponse {
  results: {
    episodeId: string
    revision: number
    ok: boolean
    status: EpisodeStatus
    /** Plain reason when refused (e.g. "Has validation problems"). */
    message: string | null
    approvalId: number | null
  }[]
}

// ---------------------------------------------------------------------------
// DELETE /api/library/episodes/<episodeId>/<revision>
//   409 when the episode was ever in an approved manifest (L11).
// ---------------------------------------------------------------------------

/** A posted video the Pi can remove: every post using it has finished and nothing scheduled needs it. */
export interface CleanupCandidate {
  videoSha256: Sha256
  bytes: number
  episodes: { episodeId: string; revision: number; batchId: string; game: string }[]
  postedOn: string[]
}
export interface CleanupPreview {
  candidates: CleanupCandidate[]
  totalBytes: number
  /** Set while a schedule approval is being processed; removal is refused then. */
  blockedReason: string | null
}
export interface CleanupResult {
  removed: Sha256[]
  refused: Sha256[]
  bytesFreed: number
}

export interface DeleteEpisodeResponse {
  deleted: true
  episodeId: string
  revision: number
  /** Bytes removed (0 when the video/cover is shared with another episode). */
  bytesFreed: number
}

// ---------------------------------------------------------------------------
// Schedule generator inputs and drafts
// ---------------------------------------------------------------------------

/** `HH:MM`, 24-hour, in `ScheduleInputs.timezone`. */
export type LocalTime = string

/** Python weekday: 0 = Monday … 6 = Sunday. */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6

export interface PlatformScheduleInput {
  include: boolean
  /** Explicit days; no default. */
  weekdays: Weekday[]
  /** Explicit times; no default. */
  times: LocalTime[]
  /** At most this many posts per local day on this platform. */
  maxPerDay: number
}

export type OrderingRule = 'game-round-robin' | 'project-mix'

/** Per-job edit applied by the generator (key = DraftJob.key). */
export type DraftEdit = { text: string } | { remove: true }

/**
 * Generator inputs (ui_schedule.generate). All values are explicit; the UI never
 * invents a cadence or timezone. Body of POST /api/schedule/drafts.
 * The backend always uses the current approved manifest (if any) as the base
 * manifest: its jobs are carried unchanged (`carried: true`).
 */
export interface ScheduleInputs {
  timezone: TimeZoneName
  startDate: IsoDate
  endDate: IsoDate
  /** Only platforms present here are considered. */
  platforms: Partial<Record<Platform, PlatformScheduleInput>>
  /** Minimum hours between posts on one account. */
  minGapHours: Partial<Record<Platform, number>>
  /** Same video on several platforms in one UTC slot: later platforms shift by k × this. */
  staggerMinutes: number
  ordering: OrderingRule
  /** project-mix only: share 0–1 per project (catalog mix targets; a project without one gets 0 and is left out). */
  mix?: Record<string, number>
  companions: {
    /** Schedule own first comments/replies where a route exists. */
    firstComment: boolean
    /** Schedule delayed answer replies (instagram/threads/bluesky) where the episode has one. */
    answerReply: boolean
  }
  /** Per-job text edits or removals. Empty object when none. */
  edits: Record<string, DraftEdit>
  /**
   * Set by the server on drafts made by POST /api/schedule/cancel or /edit: only the approved
   * manifest's jobs are carried (with `edits`), no new slots are generated, and past dates are
   * allowed. Echo it back unchanged when re-posting `draft.inputs`; the UI never sets it itself.
   */
  carryOnly?: boolean
}

export type DraftJobKind = 'post' | 'comment' | 'answer' | 'poll'

/** One job in a draft. Companion jobs have `parentKey` set. */
export interface DraftJob {
  /** `<platform>|<slotUtc>|<episodeKey>`. */
  key: string
  platform: Platform
  accountId: string
  slotUtc: IsoUtc
  slotLocal: IsoOffset
  /** Zone abbreviation as computed by the backend (display uses Intl). */
  zone: string
  kind: DraftJobKind
  /** `<questionId>` for posts, `<questionId>#comment|#answer|#poll` for companions. */
  episodeKey: string
  parentKey: string | null
  episodeId: string
  revision: number
  batchId: string
  questionId: string
  game: Game
  /** null for companions. */
  videoSha256: Sha256 | null
  coverSha256: Sha256 | null
  /** Final caption / comment text with `{link}` expanded. */
  text: string
  youtube: YoutubeText | null
  /** X thread: item 2 is the first comment, published as an immediate reply. */
  thread: string[] | null
  poll: Poll | null
  link: string | null
  /** Carried unchanged from the base (current) manifest. */
  carried: boolean
  warnings: string[]
}

export interface UnfilledSlot {
  platform: Platform
  slotLocal: IsoOffset
  /** null when the local time does not exist (DST gap). */
  slotUtc: IsoUtc | null
  reason: string
}

export interface ExcludedPlatform {
  platform: Platform
  reason: string
}

/** ui_schedule.generate output. Deterministic; no wall-clock values inside. */
export interface Draft {
  version: 1
  inputs: ScheduleInputs
  baseManifestSha256: Sha256 | null
  libraryHash: Sha256
  historyHash: Sha256
  jobs: DraftJob[]
  unfilled: UnfilledSlot[]
  excluded: ExcludedPlatform[]
  warnings: string[]
  summary: {
    /** Requested post slots. */
    requested: number
    /** Filled post slots. */
    filled: number
    /** Companion jobs added. */
    companions: number
  }
}

export type DraftStatus = 'draft' | 'requested' | 'approved' | 'superseded' | 'failed'

/**
 * Returned by POST /api/schedule/drafts, GET /api/schedule/drafts/<sha>,
 * POST /api/schedule/cancel and POST /api/schedule/edit.
 */
export interface DraftResponse {
  /** ui_schedule.draft_sha256(draft). */
  sha256: Sha256
  draft: Draft
  status: DraftStatus
  createdAt: IsoUtc
  /**
   * Problems that block approval right now (re-checked on every GET), e.g.
   * "The library changed since this draft", "An approval is already pending",
   * "Instagram is not identity-verified". Approval is refused while non-empty.
   */
  blockingProblems: string[]
  /** `APPROVE <first 8 hex of sha256>`, sent back unchanged by the Approve button (nothing is typed). */
  confirmationPhrase: string
  /** Tokenized cover URLs keyed by coverSha256 (for preview thumbnails). */
  coverUrls: Record<Sha256, MediaUrl>
}

/** POST /api/schedule/drafts/<sha>/approve body. */
export interface ApproveDraftRequest {
  /** Must equal DraftResponse.confirmationPhrase exactly. */
  confirmation: string
}

/** 202: request.json written; the applier runs asynchronously. Poll GET /api/schedule. */
export interface ApproveDraftResponse {
  status: 'requested'
  draftSha256: Sha256
  requestedAt: IsoUtc
}

// ---------------------------------------------------------------------------
// GET /api/schedule
// ---------------------------------------------------------------------------

/** Channel identity as configured (read-only), to explain exclusions before generating. */
export interface ChannelSummary {
  platform: Platform
  accountId: string | null
  route: ChannelRoute
  enabled: boolean
  identityVerified: boolean
  publishingVerified: boolean
  /** Why it cannot be scheduled, or null when schedulable. */
  blockedReason: string | null
  profileUrl: string | null
}

/** A manifest job joined with its ledger row. */
export interface QueueJob {
  /** Manifest/draft job key. */
  key: string
  /** Ledger job id once enqueued by the runner, else null. */
  jobId: string | null
  platform: Platform
  accountId: string
  slotUtc: IsoUtc
  kind: DraftJobKind
  episodeKey: string
  parentKey: string | null
  episodeId: string
  questionId: string
  game: Game
  text: string
  youtube: YoutubeText | null
  coverUrl: MediaUrl | null
  /** Ledger status, or `not-enqueued` before the runner enqueues it. */
  status: LedgerStatus | 'not-enqueued'
  statusLabel: string
  /** dispatched_at set or status ≠ ready → immutable. */
  dispatched: boolean
  /** Cancel/edit allowed (undispatched). */
  editable: boolean
  /** Why it is locked, e.g. "Dispatched 12 Oct; read-only". */
  lockReason: string | null
  permalink: string | null
  error: PlainError | null
}

export interface ScheduleResponse {
  displayTimezone: TimeZoneName
  /** Current approved manifest, or null when none. */
  manifest: {
    sha256: Sha256
    draftSha256: Sha256
    approvedAt: IsoUtc
    scope: Platform[]
    /** config.approval binds this manifest. */
    bound: boolean
    jobCount: number
  } | null
  jobs: QueueJob[]
  pendingRequest: ApprovalRequestState | null
  lastResult: ApprovalResult | null
  channels: ChannelSummary[]
  /** Most recent drafts, newest first (max 10). */
  recentDrafts: { sha256: Sha256; status: DraftStatus; createdAt: IsoUtc; jobs: number }[]
}

/** POST /api/schedule/cancel body → DraftResponse (new draft based on the current manifest). */
export interface CancelJobsRequest {
  keys: string[]
}

/** POST /api/schedule/edit body → DraftResponse. 409 if the job is dispatched. */
export interface EditJobRequest {
  key: string
  text: string
}

// ---------------------------------------------------------------------------
// GET /api/history?platform&status&game&question&q&from&to&limit&format=json|csv
// ---------------------------------------------------------------------------

export type HistoryStatus = LedgerStatus | 'cancelled'

export interface HistoryQuery {
  platform?: Platform
  status?: HistoryStatus
  game?: Game
  /** Exact questionId (companion suffixes `#…` are matched too). */
  question?: string
  /** Free-text search over episode key, caption, permalink, job id. */
  q?: string
  /** Inclusive local date in displayTimezone. */
  from?: IsoDate
  /** Inclusive local date in displayTimezone. */
  to?: IsoDate
  /** Default 200, max 1000. */
  limit?: number
  /** json (default) or csv (text/csv attachment with the same columns). */
  format?: 'json' | 'csv'
}

export interface HistoryRow {
  jobId: string
  platform: Platform
  accountId: string
  slotUtc: IsoUtc
  /** Ledger episode key. */
  episode: string
  /** episode with any `#…` suffix removed. */
  questionId: string
  kind: DraftJobKind
  game: Game | null
  episodeId: string | null
  status: HistoryStatus
  statusLabel: string
  attempts: number
  dispatchedAt: IsoUtc | null
  publishedAt: IsoUtc | null
  /** Only set for confirmed posts. */
  permalink: string | null
  error: PlainError | null
  /** First 140 characters of the caption. */
  captionPreview: string
}

export interface HistoryResponse {
  displayTimezone: TimeZoneName
  rows: HistoryRow[]
  /** Rows matching before the limit. */
  total: number
  truncated: boolean
}

// ---------------------------------------------------------------------------
// GET /api/jobs/<id>
// ---------------------------------------------------------------------------

export interface JobEvent {
  seq: number
  /** Ledger event kind (a status, `cancelled`, …). */
  kind: string
  /** Plain label for the kind. */
  label: string
  at: IsoUtc
  /** Category or short plain detail; never a vendor body. */
  detail: string
}

export interface JobDetailResponse {
  displayTimezone: TimeZoneName
  job: HistoryRow
  /** Exact published text and media reference from the payload. */
  payload: {
    caption: string
    youtube: YoutubeText | null
    thread: string[] | null
    mediaUrl: string | null
    mediaSha256: Sha256 | null
    companionOf: string | null
  }
  events: JobEvent[]
  /** Present for unresolved jobs; there is never a "post again" action. */
  reconciliation: Reconciliation | null
  manifestSha256: Sha256 | null
}

// ---------------------------------------------------------------------------
// GET /api/activity?limit&before&platform&kind&severity&format=json|csv
// ---------------------------------------------------------------------------

/** Where an activity entry comes from. */
export const ACTIVITY_KINDS = ['job', 'approval', 'library', 'system'] as const
export type ActivityKind = (typeof ACTIVITY_KINDS)[number]

export const ACTIVITY_SEVERITIES = ['info', 'success', 'warning', 'error'] as const
export type ActivitySeverity = (typeof ACTIVITY_SEVERITIES)[number]

export interface ActivityQuery {
  /** Default 100, max 500. */
  limit?: number
  /** `ActivityEntry.id` of the last entry already shown; returns strictly older entries. */
  before?: string
  platform?: Platform
  kind?: ActivityKind
  severity?: ActivitySeverity
  /** json (default) or csv (text/csv attachment with the ActivityEntry columns). */
  format?: 'json' | 'csv'
}

/**
 * One timeline entry (publisher/app/ui_activity.py). Sources: ledger events joined to their
 * job, approval request/result files, the library index, and system status (systemd unit
 * results, token health/failure markers, health.json, PAUSED). Texts are rebuilt from known
 * vocabulary: never vendor bodies, credentials or stored free text.
 */
export interface ActivityEntry {
  /** Stable, unique sort key `<IsoUtc>|<source id>`; also the `before` cursor. */
  id: string
  at: IsoUtc
  kind: ActivityKind
  /**
   * Specific event, e.g. `job.confirmed`, `job.uncertain`, `job.cancelled`, `job.owner_resolved`,
   * `job.content_exhausted`, `approval.requested`, `approval.validated-no-deploy`,
   * `approval.manifest-ready`, `approval.bound`, `approval.failed`, `approval.draft`,
   * `library.batch-imported`, `library.video-stored`, `library.cover-stored`, `library.rejected`,
   * `library.approved`, `library.withdrawn`, `library.deleted`, `system.service`,
   * `system.token-renewal-failed`, `system.token-health`, `system.publisher-health`, `system.paused`,
   * `system.metrics-on`, `system.metrics-off`, `system.metrics-read-requested`.
   */
  event: string
  severity: ActivitySeverity
  /** Plain one-line title, e.g. "Posted on Instagram". */
  title: string
  detail: string | null
  platform: Platform | null
  accountId: string | null
  /** Ledger job id: the entry opens GET /api/jobs/<id>. */
  jobId: string | null
  /** Ledger episode key, e.g. `scalar:Q1:clues#comment`. */
  episode: string | null
  episodeId: string | null
  game: Game | null
  jobKind: DraftJobKind | null
  /** Confirmed public post URL. */
  permalink: string | null
  draftSha256: Sha256 | null
  manifestSha256: Sha256 | null
  batchId: string | null
}

export interface ActivityResponse {
  generatedAt: IsoUtc
  displayTimezone: TimeZoneName
  /** Newest first. */
  entries: ActivityEntry[]
  /** Pass as `before` to load older entries; null when there are none. */
  nextBefore: string | null
}

// ---------------------------------------------------------------------------
// GET /api/activation   (display only; the UI cannot resume or enable publishing — L3)
// ---------------------------------------------------------------------------

export interface ChecklistItem {
  id: string
  label: string
  pass: boolean
  detail: string | null
  nextAction: string | null
}

export interface ActivationResponse {
  /** All items pass. */
  ready: boolean
  items: ChecklistItem[]
  /** Exact owner command, e.g. `sudo /opt/scalar-social/bin/activate.py --apply --confirm-zero-spend`. */
  command: string
  /** Read-only check command, e.g. `sudo … activate.py --check`. */
  checkCommand: string
  manifestSha256: Sha256 | null
  scope: Platform[]
  /** Plain explanation shown above the command. */
  explanation: string
}

// ---------------------------------------------------------------------------
// Pi self-update (REBUILD_CONTRACTS.md §1)
//   GET /api/system/update/status → UpdateInfo
//   POST /api/system/update/check → 202 {queued: true}
//   POST /api/system/update/start  body {confirm: "UPDATE TO <40-hex sha>"} → 202
// ---------------------------------------------------------------------------

export type UpdatePhase = 'idle' | 'checking' | 'checked' | 'staging' | 'waiting' | 'switching' | 'switched' | 'restarting' | 'complete' | 'failed'
export interface UpdateCommit { sha: string; subject: string; date: string }
export interface UpdateCheck {
  checkedAt: string; fetchOk: boolean; head: string; origin: string | null
  behind: number; ahead: number; dirty: boolean; diverged: boolean; branchOk: boolean; originOk: boolean; originUrl: string
  incoming: UpdateCommit[]            // newest first, max 30
  changes: { units: boolean; piPackage: boolean; contract: boolean; ui: boolean; files: string[] }  // files max 100
  error: string | null
}
export interface UpdateStatus {
  phase: UpdatePhase; requestId: string | null; startedAt: string | null; updatedAt: string | null
  fromCommit: string | null; toCommit: string | null; error: string | null
  log: string[]                       // last ≤ 40 lines, secrets never included
  check: UpdateCheck | null
}
export interface UpdateInfo {
  runningCommit: string | null; installKind: 'git' | 'copy'; repoHead: string | null
  restartNeeded: boolean              // repoHead !== runningCommit
  unitsChanged: boolean; piPackageChanged: boolean  // since the running commit's install of units (last apply)
  applyUnitsCommand: string | null    // shown when unitsChanged || piPackageChanged
  unitsApply: UnitsApply | null       // the automatic apply after an update (units-apply.json), null before the first
  status: UpdateStatus
}

/** units-apply.json: scalar-social-apply-units.path runs apply-units.sh --auto as root after a completed update that
 * changed unit files or pi-package*.json. queued → running → ok | failed. */
export interface UnitsApply {
  phase: 'queued' | 'running' | 'ok' | 'failed'
  commit: string | null
  at: IsoUtc | null
  error: string | null
  log: string[]                       // last lines of the run (≤ 20)
}

/** 202 body of POST /api/system/update/check and /start. */
export interface UpdateQueuedResponse {
  queued: true
}

// ---------------------------------------------------------------------------
// Library features (REBUILD_CONTRACTS.md §2): episode detail, feedback, batch notes, next batch
// ---------------------------------------------------------------------------

export const FEEDBACK_TAGS = ['keep', 'tweak', 'drop', 'hook-weak', 'too-hard', 'too-easy', 'great-reveal', 'visual-issue', 'fact-check', 'music'] as const
export type FeedbackTag = (typeof FEEDBACK_TAGS)[number]
export interface EpisodeFeedback { episodeId: string; revision: number; tags: FeedbackTag[]; note: string; status: 'open' | 'used'; updatedAt: string }
export interface BatchNote { batchId: string; kind: 'brief' | 'retro'; text: string; sha256: string; bytes: number; uploadedAt: string }
export interface BatchNotes { batchId: string; brief: BatchNote | null; retro: BatchNote | null }
/** Newest platform read of one post (metrics.py): status 'ok', or why it could not be read (authorization, not_configured, unsupported, gone, …). */
export interface PostMetrics { checkpoint: string; fetchedAt: string; status: string; values: Record<string, number> }
export interface EpisodePost { platform: string; status: string; at: string | null; permalink: string | null; metrics: PostMetrics | null }
/** One account over the last 7 complete local days (metrics.account_summary); status is 'ok' or why it could not be read. */
export interface AccountStats {
  platform: string
  followers: number | null
  followersChange: number | null
  days: number
  totals: Record<string, number>     // impressions, engagements, engagement_rate, clicks (Threads), profile_links_taps (Instagram)
  status: string
}
export interface EpisodeDetail {
  batchId: string
  episode: Record<string, unknown>    // the full batch.json episode object, as imported (creative, evidence, music, video, cover, publication, eligibility, …)
  approval: { status: string; at: string | null } | null
  notes: BatchNotes
  feedback: EpisodeFeedback | null
  posts: EpisodePost[]
}
export interface FeedbackItem extends EpisodeFeedback { batchId: string; questionId: string; game: string; format: string; styleId: string }
export interface NextBatchInfo {
  nextBatchId: string                 // YYYY-MM-bNN: the current UTC month, NN = 1 + the highest bNN seen in any month (zero-padded to 2)
  openFeedback: FeedbackItem[]
  lastBrief: BatchNote | null; lastRetro: BatchNote | null   // from the most recently imported batch that has them
  performance: EpisodePost[]          // posted jobs with permalinks; empty if none
  accounts: AccountStats[]            // account stats for the last 7 days; empty until the stats timer has run
  funnel: EpisodeFunnel[]             // one row per posted episode (metrics.funnel), newest first; empty until stats are read
  tags: FeedbackTag[]
}

// ---------------------------------------------------------------------------
// Post stats controls: GET /api/metrics/status, PUT /api/metrics/enabled, POST /api/metrics/read
// The UI only writes files in STATE/metrics/; scalar-social-metrics.{timer,path} run the reads.
// ---------------------------------------------------------------------------

export type MetricsPlatformStatus = 'ok' | 'not-configured' | 'authorization' | 'rejected' | 'error' | 'unsupported'
/** One platform in the last collector run. Status is the worst read of this run (the previous run's, with zero reads, when nothing was due). */
export interface MetricsPlatformRun {
  status: MetricsPlatformStatus
  postsRead: number                   // successful post reads this run
  accountsRead: number                // successful account reads this run
  reason: 'buffer' | null             // 'buffer': rejected because the post was made through Buffer (not a platform id)
}
/** STATE/metrics/last-run.json, written by metrics.py after every run. Never response bodies or tokens. */
export interface MetricsLastRun {
  startedAt: IsoUtc
  finishedAt: IsoUtc
  trigger: 'timer' | 'request'
  backfill: number
  outcome: 'ok' | 'stats-off' | 'bad-request' | 'error'
  platforms: Record<string, MetricsPlatformRun>
}
/** STATE/metrics/request.json: one pending manual read. */
export interface MetricsPendingRequest { requestedAt: IsoUtc; backfill: number }
export interface MetricsStatus {
  enabled: boolean                    // STATE/metrics/enabled exists: hourly reads on
  pending: MetricsPendingRequest | null
  lastRun: MetricsLastRun | null
  timer: TimerStatus | null           // scalar-social-metrics.timer
  pathActive: boolean                 // scalar-social-metrics.path is active (manual reads are picked up)
}
/** PUT /api/metrics/enabled body. */
export interface MetricsEnabledRequest { enabled: boolean }
/** POST /api/metrics/read body; backfill 0–93 days (default 0). 409 while a read is pending. */
export interface MetricsReadRequest { backfill?: number }

export type FollowsSource = 'day-metric' | 'follower-change'
/** One platform's share of an episode's funnel; null = no data. Follows are the account's for the post's local publish day, not attributed to the video. */
export interface FunnelPlatform {
  status: string | null               // newest stored post read status ('ok', 'unsupported', …), null if never read
  views: number | null
  engaged: number | null
  answered: number | null
  avgWatchSeconds: number | null
  followsThatDay: number | null
  followsSource: FollowsSource | null
}
/** Platforms whose non-null values went into each total. */
export interface FunnelCounted { views: string[]; engaged: string[]; answered: string[]; avgWatchSeconds: string[]; followsThatDay: string[] }
export interface FunnelLabels {
  project: string
  engine: Engine
  route: 'recap' | 'series' | null
  format: Format | null
  renderer: Renderer | null
  group: string
}
export interface EpisodeFunnel {
  episode: string                     // ledger episode key (contentId)
  labels: FunnelLabels | null         // from the library's newest revision of this content; null when not in the library
  publishedDates: string[]            // local YYYY-MM-DD (config timezone), ascending, unique
  views: number | null
  engaged: number | null
  answered: number | null
  avgWatchSeconds: number | null      // view-weighted mean where views are known, else plain mean; 1 decimal
  followsThatDay: number | null
  counted: FunnelCounted
  platforms: Record<string, FunnelPlatform>
}
export interface Standing {
  lastBatch: { batchId: string; importedAt: string; episodeCount: number; awaitingFiles: number } | null   // excluding legacy-*/manual-*; awaitingFiles = its episodes still missing a video or cover
  awaitingReview: number              // imported, verified, not yet content-approved
  nextPosts: { at: string; platform: string; episodeId: string }[]   // ≤ 3, from approved schedules
  openFeedback: number
  nextBatchId: string | null          // same id as GET /api/next-batch
  postedLast7Days: number             // confirmed posts (not companions) published in the last 7 days
  lastBriefAt: string | null          // uploadedAt of the latest non-empty brief / retro (last_note)
  lastRetroAt: string | null
}

/** PUT /api/library/episodes/<episodeId>/<revision>/feedback body. */
export interface FeedbackRequest {
  tags: FeedbackTag[]
  note: string
}

/** POST /api/feedback/mark-used → {updated: n}. */
export interface MarkUsedResponse {
  updated: number
}

// ---------------------------------------------------------------------------
// GET /api/backup → application/gzip attachment (Content-Disposition filename)
// GET /api/media/videos/<sha>.mp4?t=…, GET /api/media/covers/<sha>.jpg?t=… (Range supported)
// ---------------------------------------------------------------------------

/** Every endpoint, for reference and tests. */
export const ENDPOINTS = {
  health: 'GET /api/health',
  dashboard: 'GET /api/dashboard',
  pause: 'POST /api/pause',
  library: 'GET /api/library',
  importBatch: 'POST /api/library/batches',
  uploadBatchFile: 'PUT /api/library/batches/<batchId>/files/<videos|covers>/<name>',
  approveContent: 'POST /api/library/approve',
  withdrawContent: 'POST /api/library/withdraw',
  deleteEpisode: 'DELETE /api/library/episodes/<episodeId>/<revision>',
  schedule: 'GET /api/schedule',
  createDraft: 'POST /api/schedule/drafts',
  getDraft: 'GET /api/schedule/drafts/<sha>',
  approveDraft: 'POST /api/schedule/drafts/<sha>/approve',
  cancelJobs: 'POST /api/schedule/cancel',
  editJob: 'POST /api/schedule/edit',
  history: 'GET /api/history',
  activity: 'GET /api/activity',
  job: 'GET /api/jobs/<id>',
  activation: 'GET /api/activation',
  backup: 'GET /api/backup',
  mediaVideo: 'GET /api/media/videos/<sha>.mp4?t=…',
  mediaCover: 'GET /api/media/covers/<sha>.jpg?t=…',
  updateStatus: 'GET /api/system/update/status',
  updateCheck: 'POST /api/system/update/check',
  updateStart: 'POST /api/system/update/start',
  episodeDetail: 'GET /api/library/episodes/<episodeId>/<revision>',
  saveFeedback: 'PUT /api/library/episodes/<episodeId>/<revision>/feedback',
  clearFeedback: 'DELETE /api/library/episodes/<episodeId>/<revision>/feedback',
  markFeedbackUsed: 'POST /api/feedback/mark-used',
  batchNotes: 'GET /api/library/batches/<batchId>/notes',
  saveBatchNote: 'PUT /api/library/batches/<batchId>/notes/(brief|retro)',
  nextBatch: 'GET /api/next-batch',
} as const

// ---------------------------------------------------------------------------
// GET /api/catalog: publisher/catalog.json as committed (tools/export-catalog.mjs on the Mac).
// Served byte for byte with an ETag; the UI derives games, formats, styles and beds from it.
// ---------------------------------------------------------------------------

export interface CatalogFormat {
  id: string
  name: string
  engine: string
  route: string | null
  /** Scalargame: the game this format belongs to, and the short form used in episode ids. */
  game?: string
  short?: string
}

export interface CatalogGame {
  id: string
  name: string
  deepLink: string
}

export interface CatalogCheck {
  id: string
  name: string
}

export interface CatalogProject {
  id: string
  name: string
  priority: string
  order: number
  summary: string
  contractSchemaVersion: number
  formats: CatalogFormat[]
  games?: CatalogGame[]
  link: { required: boolean; site: string | null; note?: string; path?: string; inText?: string[]; bioOnly?: string[] }
  callToAction: { engage?: string; play?: string; rule?: string }
  captions: { language: string; hashtags: Record<string, string[]>; firstComment: unknown; poll: boolean; youtubeTitleSuffix: string }
  budget: { monthlyUsd: number; perRunApproval?: boolean; note?: string }
  mix: { share: number; target: number | null; note?: string }
  checks: CatalogCheck[]
}

export interface CatalogTemplate {
  format: string
  component: string
  durationSeconds: number
  revealSeconds: number
}

export interface CatalogStyle {
  id: string
  game: string
  version: number
  summary: string
}

export interface CatalogBed {
  id: string
  game: string
  durationSeconds: number
  revealSeconds: number
  title: string
  artist: string | null
  license: string
  sourceUrl: string | null
  /** Retired beds (the owner's local-only tracks) are never offered and never served. */
  retired: boolean
}

export interface CatalogRouteInput {
  name: string
  type: 'string' | 'integer'
  required: boolean
  description: string
}

export interface CatalogRoute {
  id: string
  name: string
  description: string
  inputs: CatalogRouteInput[]
  paidServices: string[]
  freeServices: string[]
  localTools: string[]
  formats: string[]
}

export interface CatalogVideoModel {
  id: string
  name: string
  provider: string
  tier: string
  costPerSecondUsd: number
  costPerSecondWithAudioUsd?: number | null
  maxResolution: string
  maxDurationSeconds: number
  clipSeconds?: number
  audio: boolean
  referenceImages: boolean
  description: string
  verifiedAt?: string
}

export interface CatalogEngine {
  id: string
  name: string
  summary: string
  kitVersion: string
  routes: CatalogRoute[]
  templates?: CatalogTemplate[]
  styles?: CatalogStyle[]
  beds?: CatalogBed[]
  defaultModels?: Record<string, string>
  tierDefaults?: Record<string, string>
  fallbackOrder?: Record<string, string[]>
  videoModels?: CatalogVideoModel[]
}

export interface CatalogChannel {
  id: string
  name: string
  profileUrl: string | null
  captionLimit: number
  firstComment: boolean
  linkInText: boolean
}

export interface Catalog {
  catalogVersion: 1
  studio: { name: string; summary: string; flow: string[] }
  projects: CatalogProject[]
  engines: CatalogEngine[]
  channels: CatalogChannel[]
}

// ---------------------------------------------------------------------------
// GET /api/assets/motion/manifest: the motion engine's public files the Pi serves for in-browser preview and export
// (publisher/motion-assets.json). Files: GET <base>/<path> (session cookie; immutable, ETag = sha256, Range).
// ---------------------------------------------------------------------------

export interface MotionManifest {
  version: string
  /** e.g. `/api/assets/motion/<version>`: staticFile() resolves against it. */
  base: string
  files: Record<string, { bytes: number; sha256: Sha256 }>
}

// ---------------------------------------------------------------------------
// /api/studio/*: the story worker agent on the laptop (engines/story/src/agent.py), through the Pi's studio proxy
// (publisher/app/studio_proxy.py). 503 "Worker offline" when the laptop sleeps or the worker is not set up.
// ---------------------------------------------------------------------------

export type StoryRoute = 'recap' | 'series'
export type StoryStatus = 'created' | 'running' | 'paused' | 'review' | 'scene_failed' | 'error' | 'completed'
export type StoryStepName = 'writer' | 'screenwriter' | 'casting' | 'world_builder' | 'director' | 'set_designer' | 'scene_generator' | 'editor'

export interface StoryOriginalsBudget {
  monthlyUsd?: number
  perRunApproval?: boolean
}

export interface StoryHealth {
  ok: boolean
  version: string
  engine: 'story'
  running: string[]
  keys: Record<string, boolean>
  paidRunsEnabled: boolean
  originalsBudget: StoryOriginalsBudget
}

export interface StoryFailedScene {
  episode: number | null
  scene: number | null
  prompt: string | null
  error: string
}

export interface StoryProject {
  id: string
  name: string
  route: StoryRoute
  params: { project_title?: string; brief?: string; num_episodes?: number; video_model?: string; max_budget?: number }
  status: StoryStatus
  running: boolean
  currentStep: string | null
  createdAt: string
  updatedAt: string
  error: string | null
  videoModel: string
  spentUsd: number
  maxBudgetUsd: number
  /** Recap only: the script waiting for review (or the approved one). */
  script?: Record<string, unknown> | null
  scriptApproved?: boolean
  failedScene: StoryFailedScene | null
}

export interface StoryStepState {
  completed: boolean
  startedAt: string | null
  completedAt: string | null
  error: string | null
  artifacts: number
}

export interface StoryPipelineState {
  seriesSteps: Partial<Record<StoryStepName, StoryStepState>>
  episodes: Record<string, Partial<Record<StoryStepName, StoryStepState>>>
}

export interface StoryProjectDetail extends StoryProject {
  pipelineState: StoryPipelineState | null
}

export interface StoryEvent {
  seq: number
  at: string
  kind: string
  message: string
  step?: number | string
  data?: Record<string, string | number | boolean>
}

export interface StoryEvents {
  events: StoryEvent[]
  last: number
  running: boolean
  status: StoryStatus
}

export interface StoryEstimate {
  estimateUsd: number
  lines: { what: string; usd: number }[]
  unpriced: string[]
  token: string
  spentUsd: number
  maxBudgetUsd: number
  paidRunsEnabled: boolean
  originalsBudget: StoryOriginalsBudget
}

export interface StoryConfirm {
  token: string
  estimateUsd: number
}

export interface StoryArtifact {
  path: string
  bytes: number
  kind: 'image' | 'video' | 'json' | 'text' | 'file'
  json: unknown
}

export interface StoryArtifacts {
  step: StoryStepName
  episode: number | null
  files: StoryArtifact[]
}

export interface StoryRender {
  id: string
  episodeId: string | null
  route: string | null
  createdAt: string | null
  video: { file?: string; durationSeconds?: number; width?: number; height?: number; bytes?: number } | null
  costUsd: number | null
  credits: unknown
  disclosure: unknown
}

export interface StoryVideoModel {
  id: string
  name: string
  provider: string
  costPerSecondUsd: number
  maxResolution: string
  maxDurationSeconds: number
  audio: boolean
  referenceImages: boolean
  description: string
  episodeUsd: number
  clipSeconds?: number
  available?: boolean
}

export type StoryTier = 'cheapest' | 'recommended' | 'high_fidelity'

export interface StoryModels {
  llm_model: string
  image_model: string
  tts_model: string
}

export interface StoryPreset extends StoryModels {
  tier: StoryTier
}

export interface StorySettings {
  models: StoryModels
  choices: Record<keyof StoryModels, string[]>
  video: { active_model: string; active_tier: StoryTier; max_budget: number; auto_downgrade: boolean }
  tiers: Partial<Record<StoryTier, StoryVideoModel[]>>
  presets: Record<string, StoryPreset>
  keys: Record<string, boolean>
}

export type StorySettingsUpdate = Partial<StoryModels> & {
  active_tier?: StoryTier
  active_model?: string
  max_budget?: number
  auto_downgrade?: boolean
}

export type StorySceneAction = 'retry' | 'edit' | 'skip' | 'change_model'
