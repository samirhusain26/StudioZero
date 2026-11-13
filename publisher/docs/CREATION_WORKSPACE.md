# Local creation workspace

The creation workspace stores unfinished cuts separately from the finalized publishing library. It does not create publishing batches, register projects, finalize media, approve a publishing package, or schedule posts.

## External handoff and return

Start in Studio, choose a project, and save a short brief. Copy the resulting prompt into a repository-enabled agent. Copying a prompt does not start a job. Preserve the production ID supplied by StudioZero.

Return a `manifest.json` and the files it names. The manifest is a creation artifact descriptor, **not** `batch.json` and not a publishing contract. Example shape (replace the example identity, byte count and digest with the exact saved production and actual file values):

```json
{
  "productionId": "production-from-studio",
  "project": "scalargame",
  "revisionId": "cut-r1",
  "batchId": null,
  "episodeId": null,
  "files": [
    {
      "path": "cut.mp4",
      "size": 123,
      "sha256": "replace-with-the-64-character-lowercase-sha256",
      "mediaType": "video/mp4",
      "role": "video"
    }
  ]
}
```

Use flat, unique filenames. At least one MP4 must have the `video` role. Optional plain-text or JSON scripts/transcripts, captions and evidence, and PNG/JPEG covers can be returned with their declared roles; no transcript is invented when absent. Each file is limited to 256 MiB (JSON artifacts to 1 MB), with at most 64 files per revision. The app validates the supplied identity and hashes before returning files; the server verifies bytes and probes the video again. Engine batch/episode IDs, when assigned, must remain stable on subsequent revisions. A new revision needs a new revision ID. Retrying an identical import is safe. Failed replacement leaves the prior revision available.

The private API stages files under `/api/creation/<production>/staging/<fileId>` before committing the manifest. `fileId` is the transport filename added by the app; external manifests need only the fields above. Explainers returns and cut decisions also send the displayed `expectedResearchVersion`, so an older tab cannot approve changed research. Creation state and immutable revision artifacts live below the configured server state directory's `creation/` folder. Back up that folder along with the rest of local state.

## Decisions and project boundaries

- Cut approval belongs to an exact creation revision. Returning a replacement requires a new decision. Feedback remains attached to the cut it describes.
- Publishing still uses the existing finalized folder importer, including its `READY_FOR_UPLOAD` check, followed by exact library content/caption approval and schedule approval. A creation cut approval is none of those approvals.
- Explainers starts with topic research. The question, supported angle and sources are retained with research decisions. A research hold blocks cut admission and approval. Accepting an angle in this UI does not approve C2, C3 or C4, or resolve the voice/pilot acceptance gates in the project workflow.
- Marathon is private, manual delivery. No publisher scheduling is available for its creation records.
- Originals remains on hold. The UI does not authorize a generation run or its cost.

No creation endpoint invokes an engine, provider, publisher or deployment operation. The existing browser-based Scalargame preview/export path remains separate and retains its own checks and explicit finalization flow.
