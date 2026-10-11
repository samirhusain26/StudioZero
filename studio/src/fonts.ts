import { staticFile } from 'remotion';
import { loadFont } from '@remotion/fonts';
import fraunces900 from '@fontsource/fraunces/files/fraunces-latin-900-normal.woff2';
import fraunces700 from '@fontsource/fraunces/files/fraunces-latin-700-normal.woff2';
import mono500 from '@fontsource/geist-mono/files/geist-mono-latin-500-normal.woff2';
import mono700 from '@fontsource/geist-mono/files/geist-mono-latin-700-normal.woff2';

void staticFile;
loadFont({ family: 'Fraunces', url: fraunces900, weight: '900' });
loadFont({ family: 'Fraunces', url: fraunces700, weight: '700' });
loadFont({ family: 'Geist Mono', url: mono500, weight: '500' });
loadFont({ family: 'Geist Mono', url: mono700, weight: '700' });
