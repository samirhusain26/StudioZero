# Next batch

Library › **Make a batch** turns what you learned into the next batch. It is the Mac step shown on the Pi, as five numbered steps; each says whether it happens here on the Pi or on the Mac. Home's loop points here when the last batch is getting old, nothing is scheduled soon, or there is feedback to carry over.

1. **Carry feedback over (Pi).** Read the open feedback (Show notes; notes may name answers), the last retro and brief (each behind its own Show button) and how the posts did. Press Download feedback.json and move `feedback-<batchId>.json` into `~/Personal/code_projects/scalargame/marketing/library/_inbox/` on the Mac (that folder is not in git).
2. **Write the brief (Pi).** Show brief and edit the draft, prefilled from the feedback: what to change, keep, try or avoid. Press Copy prompt for Claude. It copies exactly:

```text
/video-batch brief <batchId>

<your brief>

Feedback file: library/_inbox/feedback-<batchId>.json
```

3. **Let Claude make it (Mac).** Start Claude in the marketing folder and paste the prompt (see [Make a batch](#make-a-batch)). Tick each checkpoint as you approve it; the checklist is only kept in this browser, and it is cleared once the batch arrives on the Pi.
4. **Upload it (Pi).** Drop the finalized folder there (or in the Library), then review the episodes.
5. **Retro, after posting (Mac).** Ask Claude for `/video-batch retro <batchId>`, add the RETRO.md it writes as the batch's retro note, then mark the feedback you used as used.
