import { request, upload, type UploadContentType, type UploadProgress } from './client'

export interface CreationArtifact { path: string; size: number; sha256: string; mediaType: string; role: string; fileId: string }
export interface CreationRevision { id: string; createdAt: string; manifest: { batchId?: string | null; episodeId?: string | null }; artifacts: CreationArtifact[]; cutApproval: { revisionId: string; approvedAt: string } | null }
export interface Production {
  id: string; project: string; brief: string; title?: string | null; options?: Record<string, string> | null
  manualDeliveries?: Array<{ revisionId: string; reportedAt: string; url: string | null }>
  createdAt: string; updatedAt: string; currentRevisionId: string | null; revisions: CreationRevision[]
  research: { status: 'not-started' | 'held' | 'accepted'; question?: string; angle?: string; sources?: string[]; version?: number; history?: Array<Record<string, unknown>> }; decisions: Array<{ revisionId: string; decision: string; feedback?: Array<{ text: string; time?: number }>; at: string }>
}
export interface StagedFile { fileId: string; size: number; sha256: string; mediaType: string }

const enc = encodeURIComponent
export const creationApi = {
  list: () => request<{ productions: Production[] }>('GET', '/api/creation'),
  get: (id: string) => request<Production>('GET', `/api/creation/${enc(id)}`),
  create: (body: { id: string; project: string; brief: string; title?: string; options?: Record<string, string> }) => request<Production>('POST', '/api/creation', { json: body }),
  stage: (id: string, file: File, fileId: string, onProgress?: (progress: UploadProgress) => void) =>
    upload<StagedFile>('PUT', `/api/creation/${enc(id)}/staging/${enc(fileId)}`, file, file.type as UploadContentType, onProgress).promise,
  revise: (id: string, expectedRevisionId: string | null, manifest: Record<string, unknown>, expectedResearchVersion?: number) =>
    request<Production>('POST', `/api/creation/${enc(id)}/revisions`, { json: { expectedRevisionId, manifest, expectedResearchVersion } }),
  decide: (id: string, expectedRevisionId: string, decision: 'approve-cut' | 'request-revision', feedback?: Array<{ text: string; time?: number }>, expectedResearchVersion?: number) =>
    request<Production>('POST', `/api/creation/${enc(id)}/decisions`, { json: { expectedRevisionId, decision, feedback, expectedResearchVersion } }),
  research: (id: string, expectedVersion: number, status: 'held' | 'accepted', question: string, angle: string, sources: string[]) =>
    request<Production>('POST', `/api/creation/${enc(id)}/research`, { json: { expectedVersion, status, question, angle, sources } }),
  manualDelivery: (id: string, expectedRevisionId: string, url?: string) =>
    request<Production>('POST', `/api/creation/${enc(id)}/delivery`, { json: { expectedRevisionId, url: url || null } }),
}
