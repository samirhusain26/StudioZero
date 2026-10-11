import React from 'react';
import { Audio, Sequence, staticFile } from 'remotion';

export type SfxName =
  | 'thock' | 'tick' | 'tock' | 'flip' | 'ding' | 'shake' | 'stamp' | 'rewind' | 'whip' | 'pop'
  | 'swoosh' | 'poweroff' | 'sparkle' | 'hit' | 'riser' | 'chime' | 'ocean'
  | `note${0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9}`;

/** One sound effect starting at frame `at` (public/sfx/<name>.wav). */
export const Sfx: React.FC<{ at: number; name: SfxName; volume?: number }> = ({ at, name, volume = 1 }) => (
  <Sequence from={Math.round(at)} layout="none" name={`sfx:${name}`}>
    <Audio src={staticFile(`sfx/${name}.wav`)} volume={volume} />
  </Sequence>
);
