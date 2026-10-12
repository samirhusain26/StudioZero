import type { Route, Screen } from '../views'
import { GUIDE } from './guide'

/**
 * Per-screen "What to do here" help (REBUILD_CONTRACTS.md §4). Each entry links to a fixed guide
 * anchor; a test checks every anchor exists in the bundled guide.
 */
export interface ScreenHelpEntry {
  /** Guide anchor for "More in the Guide →". */
  anchor: string
  /** 2–4 short lines. */
  lines: string[]
}

export const SCREEN_HELP = {
  home: {
    anchor: 'how-it-works',
    lines: [
      'Your loop: Make → Upload → Review → Schedule → Post → Learn, then the next batch.',
      'The highlighted step is the one thing to do now. Tap any step for its status.',
      'Platforms show three separate marks: a passed test does not mean publishing is on.',
      'The autopilot schedules and posts approved videos by itself. Pause is in Settings.',
    ],
  },
  studio: {
    anchor: 'studio',
    lines: [
      'Studio is the Make step for every project: Originals and Scalargame.',
      'Each project shows its formats, budget, mix and how far its approved schedule reaches.',
      'Make a batch builds the prompt for Claude from what the engines can make.',
    ],
  },
  export: {
    anchor: 'export-in-the-browser',
    lines: [
      'Open the batch\'s job bundle (web-jobs.json); it stays in this browser.',
      'Preview any episode, then export: each one is rendered, mastered and checked here, on this device.',
      'When every episode passed, finalize and upload: the Pi validates everything again.',
    ],
  },
  newFormat: {
    anchor: 'new-format-style-or-project',
    lines: [
      'Describe a new format, a new look for a game, or a new project; only engines and options the catalog has are offered.',
      'Copy the prompt into Claude Code on the Mac: it builds the template and one pilot, then stops for your review.',
      'Watch the pilot in Studio › Export (motion) or Story renders (story) before anything else happens.',
    ],
  },
  jobs: {
    anchor: 'story-jobs',
    lines: [
      'Story jobs run on the laptop worker: recaps and animated series for Originals.',
      'Create a job here, then open it to see each step, its files and what it has spent.',
      'Nothing paid starts until you confirm a cost estimate; the worker checks the budget again.',
    ],
  },
  job: {
    anchor: 'story-jobs',
    lines: [
      'Run shows the cost estimate first; nothing paid starts until you confirm it.',
      'A recap stops for you to review its script; a failed scene waits for retry, edit, skip or another model.',
      'Cancel stops before the next paid step. Click a finished step to see its files.',
    ],
  },
  renders: {
    anchor: 'story-jobs',
    lines: ['Every finished story video on the laptop, with its cost and credits.', 'Videos stream from the laptop through the Pi; nothing is stored here.'],
  },
  storySettings: {
    anchor: 'story-jobs',
    lines: [
      'Models and the video tier for the next story runs. Changes apply at once.',
      'API keys stay in the laptop\'s .env: this page only says whether each one is set.',
    ],
  },
  library: {
    anchor: 'upload-a-batch',
    lines: [
      'Upload: drop the finalized batch folder from the Mac anywhere on this page, or choose it.',
      'Review: To review lists what waits for you. Tap an episode to watch it, approve it and leave feedback.',
      'Approving does not schedule anything; that happens in Schedule.',
    ],
  },
  episode: {
    anchor: 'review-episodes',
    lines: [
      'Watch the video and read the captions. The answer stays hidden until you press Reveal answer.',
      'Approve, or tap Feedback to tag what to keep or fix; feedback goes into the next batch.',
      'Next goes to the following episode of the list you came from.',
    ],
  },
  schedule: {
    anchor: 'schedule',
    lines: [
      'Pick a start date and tap Generate draft: the recommended plan is one post per platform per day.',
      'Customize opens every field, already filled with that plan.',
      'Check each job’s time, platform and exact text; edit or remove entries to make a new draft.',
      'Nothing posts until a draft is approved. The autopilot also adds the next draft when under a week is left.',
    ],
  },
  approval: {
    anchor: 'approve-a-schedule',
    lines: [
      'Approve is enabled when nothing blocks the draft.',
      'Approving deploys and checks the media, then publishing starts automatically (not while paused).',
    ],
  },
  make: {
    anchor: 'make-a-batch',
    lines: [
      'Pick the project with the chips; videos are made by Claude, this page walks you through it, top to bottom.',
      'Choose the mix from the catalog, copy the prompt, then follow the checkpoints on the Mac.',
      'Upload the finalized folder in step 4. After posting, add the retro in step 5.',
    ],
  },
  update: {
    anchor: 'update-the-pi',
    lines: [
      'Check for updates asks the Pi to look at GitHub; nothing changes until you confirm.',
      'Read “What’s new” and any warnings, then review the full commit id and confirm Update.',
      'The page reloads by itself when the Pi runs the new version.',
    ],
  },
  activity: {
    anchor: 'health',
    lines: [
      'Everything the Pi did, newest first. Chips pick what to show: Posts is the posting history.',
      'Search by question id, job id or platform; more filters and CSV/JSON export are under ⋯.',
      'Open an entry with a job to see its events. Uncertain jobs are never posted again from here.',
    ],
  },
  activation: {
    anchor: 'activation',
    lines: [
      'The autopilot runs this checklist itself after each approval and twice a day.',
      'A FAIL item holds it until fixed. Resuming after a pause is an owner command on the Pi.',
    ],
  },
} as const satisfies Record<string, ScreenHelpEntry>

export type ScreenHelpId = keyof typeof SCREEN_HELP

/** Settings sections with a more specific guide section than the page's. */
export const SETTINGS_SECTION_ANCHORS: Record<string, string> = {
  activation: 'activation',
  update: 'update-the-pi',
  system: 'health',
}

/** The guide anchor the header help icon opens: the screen map in content/guide/meta.json. */
export function helpAnchor(route: Route, screen: Screen): string {
  return (route.section && SETTINGS_SECTION_ANCHORS[route.section]) || GUIDE.meta.screens[screen] || 'how-it-works'
}
