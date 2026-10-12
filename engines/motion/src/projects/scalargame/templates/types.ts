import type {SfxName} from '../../../kit/sfx';
import type {LibraryEpisodeProps, StyleTokens, Timing} from '../types';

export type TemplateProps = {ep: LibraryEpisodeProps; s: StyleTokens; t: Timing};
/** A template renders the whole frame (background to closing card) from props alone; audio is added by LibraryEpisode. */
export type Template = {
  Component: React.FC<TemplateProps>;
  /** Extra purposeful SFX beyond the standard item/choices/think/reveal/cta cues (seconds). */
  extraCues?: (p: TemplateProps) => {at: number; name: SfxName; volume?: number}[];
};
