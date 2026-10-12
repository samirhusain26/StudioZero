/** The fixed safety lines every prompt the Studio builds ends with (brief: "Prompt builder"). Never configurable. */
export const SAFETY_LINES = [
  'Safety (fixed; part of every Studio prompt):',
  '- Never finalize or upload a batch without my explicit approval for that batch; approving, finalizing and uploading stay with me.',
  '- Facts only from frozen sources (library/_sources/<snapshot>/ or the batch’s recorded sources), never from memory.',
  '- Credit every third-party or generated asset (render.json credits; the TMDB notice wherever TMDB data or images appear).',
  '- Paid generation only within the project’s budget and only after I confirm a cost estimate for that run.',
] as const
