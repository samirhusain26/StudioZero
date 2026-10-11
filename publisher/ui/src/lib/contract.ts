/**
 * Text limits mirrored from contract/library_contract.py. The backend
 * re-validates everything; these power live counters in the forms.
 */
import type { CaptionPlatform, CommentPlatform, Game } from '../api/types'
import { LINK_PLATFORMS } from '../api/types'

export const SITE = 'https://www.scalargame.com'
export const CAPTION_LIMITS: Record<CaptionPlatform, number> = {
  instagram: 2200, facebook: 2200, threads: 500, x: 280, bluesky: 300, tiktok: 2200,
}
export const COMMENT_LIMITS: Record<CommentPlatform, number> = { instagram: 2200, threads: 500, bluesky: 300, x: 280 }
export const X_URL_WEIGHT = 23
export const YOUTUBE_TITLE_LIMIT = 100
export const YOUTUBE_DESCRIPTION_BYTES = 5000
export const ALT_TEXT_LIMIT = 1000
export const MAX_HASHTAGS = 30
export const POLL_OPTION_LIMIT = 25
export const MAX_VIDEO_BYTES = 24_000_000
export const MAX_COVER_BYTES = 2_000_000
export const MAX_BATCH_JSON_BYTES = 1_000_000
/** answerReply must fit every reply route. */
export const ANSWER_REPLY_LIMIT = Math.min(COMMENT_LIMITS.instagram, COMMENT_LIMITS.threads, COMMENT_LIMITS.bluesky)
export const MANUAL_UTM_CAMPAIGN = 'social_manual_v1'

/** Provider per-day caps the generator applies (DESIGN.md). */
export const PROVIDER_DAILY_CAPS: { label: string; limit: number }[] = [
  { label: 'Facebook', limit: 30 },
  { label: 'Instagram', limit: 25 },
  { label: 'Threads', limit: 250 },
  { label: 'Bluesky', limit: 25 },
  { label: 'Buffer routes (X, YouTube, TikTok) combined', limit: 40 },
]

/** Length in Unicode code points (Python len()), not UTF-16 units. */
export function codePoints(text: string): number {
  let n = 0
  for (const _ of text) n++
  return n
}

export function utf8Bytes(text: string): number {
  return new TextEncoder().encode(text).length
}

/** library_contract.text_length: X weighs each URL as 23 characters. */
export function textLength(platform: string, text: string): number {
  if (platform === 'x') {
    const urls = text.match(/https?:\/\/\S+/g) ?? []
    return codePoints(text.replace(/https?:\/\/\S+/g, '')) + X_URL_WEIGHT * urls.length
  }
  return codePoints(text)
}

export function isLinkPlatform(platform: string): boolean {
  return (LINK_PLATFORMS as readonly string[]).includes(platform)
}

/** library_contract.link_for. */
export function linkFor(deepLink: string, utmCampaign: string, platform: string, episodeId: string): string {
  const query = new URLSearchParams({
    utm_source: platform,
    utm_medium: 'organic_social',
    utm_campaign: utmCampaign,
    utm_content: episodeId,
  })
  return `${SITE}${deepLink}?${query.toString()}`
}

/** Episode id used to estimate `{link}` length before the Pi assigns the real one (`<game>-manual-YYYYMMDD-<nnn>`, UTC date). */
export function estimatedManualEpisodeId(game: Game, now: Date = new Date()): string {
  return `${game}-manual-${now.toISOString().slice(0, 10).replaceAll('-', '')}-001`
}

export interface CounterState {
  length: number
  limit: number
  over: boolean
  remaining: number
  /** Plain label, e.g. "212 / 280" or "12 over the 280 limit". */
  label: string
}

export function counter(length: number, limit: number): CounterState {
  const over = length > limit
  return {
    length,
    limit,
    over,
    remaining: limit - length,
    label: over ? `${length - limit} over the ${limit} limit` : `${length} / ${limit}`,
  }
}

/** Counter for a caption/comment with `{link}` expanded as the Pi will. */
export function captionCounter(
  platform: string,
  text: string,
  limit: number,
  link: { deepLink: string; utmCampaign: string; episodeId: string },
): CounterState {
  const expanded = text.includes('{link}')
    ? text.split('{link}').join(linkFor(link.deepLink, link.utmCampaign, platform, link.episodeId))
    : text
  return counter(textLength(platform, expanded), limit)
}

/** Problems the form can detect before sending (the Pi re-validates). */
export function captionIssues(platform: string, text: string): string[] {
  const issues: string[] = []
  const placeholders = [...text.matchAll(/\{([^{}]*)\}/g)].map((m) => m[1])
  if (placeholders.some((p) => p !== 'link')) issues.push('Only {link} is expanded; remove other {…} placeholders.')
  if (text.includes('{link}') && !isLinkPlatform(platform)) issues.push('This platform does not show clickable links; remove {link}.')
  return issues
}

export function hashtagCount(text: string): number {
  return (text.match(/(?<!\w)#\w+/g) ?? []).length
}
