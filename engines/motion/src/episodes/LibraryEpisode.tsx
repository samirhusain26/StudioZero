// One composition for every library episode: picks the format template and style recipe, adds the music bed and the
// SFX cue sheet derived from the shared timing. Props come from library/<batch>/review/jobs/<episodeId>/input.json.
import React from 'react';
import {AbsoluteFill, Audio, staticFile, type CalculateMetadataFunction} from 'remotion';
import {Sfx} from '../kit/sfx';
import {libraryFontsReady} from './fonts';
import {STYLES} from './styles';
import {TEMPLATES} from './templates';
import {assertTiming, f} from './timing';
import {SafeArea} from './kit/ui';
import type {LibraryEpisodeProps} from './types';

void libraryFontsReady;

export const LibraryEpisode: React.FC<LibraryEpisodeProps> = (ep) => {
  const s = STYLES[ep.styleId];
  if (!s) throw new Error(`Unknown style ${ep.styleId}`);
  if (s.game !== ep.q.game) throw new Error(`Style ${ep.styleId} is for ${s.game}, episode is ${ep.q.game}`);
  const t = ep.timing;
  assertTiming(t, ep.q.format);
  const template = TEMPLATES[ep.q.format];
  const props = {ep, s, t};
  const v = ep.sfxVolume;
  const cues = [
    ...t.items.map((at) => ({at, name: s.sfx.item, volume: 0.7})),
    {at: t.choicesIn, name: s.sfx.choices, volume: 0.6},
    {at: t.infoComplete, name: s.sfx.think, volume: 0.35},
    {at: t.reveal, name: s.sfx.reveal, volume: 1},
    ...(s.sfx.explain ? [{at: t.explain, name: s.sfx.explain, volume: 0.5}] : []),
    {at: t.cta, name: s.sfx.cta, volume: 0.6},
    ...(template.extraCues?.(props) ?? []),
  ];
  return (
    <AbsoluteFill style={{background: s.bg}}>
      <template.Component {...props} />
      {ep.music && <Audio src={staticFile(`episodes/music/${ep.music.bed}`)} volume={ep.music.volume} />}
      {cues.map((c, i) => <Sfx key={i} at={f(c.at)} name={c.name} volume={(c.volume ?? 1) * v} />)}
      {ep.showSafeArea && <SafeArea />}
    </AbsoluteFill>
  );
};

export const calculateLibraryMetadata: CalculateMetadataFunction<LibraryEpisodeProps> = ({props}) => ({
  durationInFrames: props.durationInFrames,
});
