import React from 'react';
import { Composition } from 'remotion';
// Fraunces 700 (Whenabouts body text) is only registered here; the episode fonts cover the other weights.
import './fonts';
import { LibraryEpisode, calculateLibraryMetadata } from './projects/scalargame/LibraryEpisode';
import { FPS } from './projects/scalargame/timing';
import type { LibraryEpisodeProps } from './projects/scalargame/types';
import librarySample from './projects/scalargame/sample-props.json';

export const Root: React.FC = () => (
  <>
    <Composition id="LibraryEpisode" component={LibraryEpisode} durationInFrames={600} fps={FPS} width={1080} height={1920} defaultProps={librarySample as unknown as LibraryEpisodeProps} calculateMetadata={calculateLibraryMetadata} />
  </>
);
