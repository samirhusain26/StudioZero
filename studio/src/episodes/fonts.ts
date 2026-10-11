// Licensed font files bundled in public/episodes/fonts (SIL OFL 1.1; licences in public/episodes/fonts/licenses).
import {staticFile} from 'remotion';
import {loadFont} from '@remotion/fonts';

const FILES: [family: string, file: string, weight: string, style?: 'normal' | 'italic'][] = [
  ['Fraunces', 'fraunces-latin-600-normal.woff2', '600'],
  ['Fraunces', 'fraunces-latin-900-normal.woff2', '900'],
  ['Fraunces', 'fraunces-latin-600-italic.woff2', '600', 'italic'],
  ['Fraunces', 'fraunces-latin-900-italic.woff2', '900', 'italic'],
  ['Geist Mono', 'geist-mono-latin-500-normal.woff2', '500'],
  ['Geist Mono', 'geist-mono-latin-700-normal.woff2', '700'],
  ['Montserrat', 'montserrat-latin-600-normal.woff2', '600'],
  ['Montserrat', 'montserrat-latin-800-normal.woff2', '800'],
  ['Montserrat', 'montserrat-latin-900-normal.woff2', '900'],
  ['IBM Plex Mono', 'ibm-plex-mono-latin-500-normal.woff2', '500'],
  ['IBM Plex Mono', 'ibm-plex-mono-latin-700-normal.woff2', '700'],
  ['Nunito', 'nunito-latin-700-normal.woff2', '700'],
  ['Nunito', 'nunito-latin-800-normal.woff2', '800'],
  ['Nunito', 'nunito-latin-900-normal.woff2', '900'],
];

export const libraryFontsReady = Promise.all(
  FILES.map(([family, file, weight, style = 'normal']) => loadFont({family, url: staticFile(`episodes/fonts/${file}`), weight, style})),
);

export const FONT = {
  fraunces: 'Fraunces, serif',
  geist: '"Geist Mono", monospace',
  montserrat: 'Montserrat, sans-serif',
  plex: '"IBM Plex Mono", monospace',
  nunito: 'Nunito, sans-serif',
};
