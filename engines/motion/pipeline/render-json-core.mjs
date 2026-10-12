// Pure core of the motion engine's render.json (tools/RENDER_JSON.md; no Node or browser APIs): shared by render.mjs
// (render.sh renders, via render-json.mjs) and the Studio's browser export (publisher/ui, web renders).
export const FONTS = {
  fraunces: {title: 'Fraunces', creator: 'The Fraunces Project Authors', sourceUrl: 'https://github.com/undercasetype/Fraunces'},
  geist: {title: 'Geist Mono', creator: 'The Geist Project Authors', sourceUrl: 'https://github.com/vercel/geist-font'},
  montserrat: {title: 'Montserrat', creator: 'The Montserrat Project Authors', sourceUrl: 'https://github.com/JulietaUla/Montserrat'},
  plex: {title: 'IBM Plex Mono', creator: 'IBM Corp.', sourceUrl: 'https://github.com/IBM/plex'},
  nunito: {title: 'Nunito', creator: 'The Nunito Project Authors', sourceUrl: 'https://github.com/googlefonts/nunito'},
};
// Data the templates draw: maps (Scalar locator, Tectonic) and World Bank figures (Continuum).
export const DATA = {
  scalar: [{kind: 'data', title: 'Natural Earth map geometry', creator: 'Natural Earth', sourceUrl: 'https://www.naturalearthdata.com/',
    license: 'public-domain', attribution: 'Made with Natural Earth', sha256: null}],
  tectonic: [{kind: 'data', title: 'Natural Earth map geometry', creator: 'Natural Earth', sourceUrl: 'https://www.naturalearthdata.com/',
    license: 'public-domain', attribution: 'Made with Natural Earth', sha256: null}],
  continuum: [{kind: 'data', title: 'World Bank population and area figures', creator: 'World Bank', sourceUrl: 'https://data.worldbank.org/',
    license: 'CC-BY-4.0', attribution: 'World Bank Open Data (CC BY 4.0)', sha256: null}],
  whenabouts: [],
};
export const AI_BED = bed => bed.license === 'owner-supplied' && /AI-generated/.test(bed.rights ?? '');

/**
 * The render.json document for one validated episode. `job` carries the renderer's own facts (render.sh: codeHash
 * and coverFrame from status.json; web: the UI bundle's commit); `fonts` are the style's FONT ids; `bed` is the
 * beds.json entry of `bedId`.
 */
export function motionRenderJsonCore({input, createdAt, job, video, cover, bed, bedId, fonts}) {
  const game = input.props.q.game;
  if (!bed) throw new Error(`${input.episodeId}: unknown music bed ${bedId}`);
  const aiBed = AI_BED(bed);
  return {
    renderJsonVersion: 1, engine: 'motion', route: null, kitVersion: input.kitVersion, project: 'scalargame',
    episodeId: input.episodeId, createdAt,
    job: {revision: input.revision, contentKey: input.questionKey, contentId: input.questionId, styleId: input.styleId,
      musicBed: bedId, propsHash: input.propsHash, ...job},
    video: {file: 'render.mp4', sha256: video.sha256, bytes: video.bytes, durationSeconds: video.durationSeconds, width: video.width, height: video.height,
      fps: video.fps, videoCodec: video.videoCodec, audioCodec: video.audioCodec},
    cover: {file: 'cover.jpg', sha256: cover.sha256, bytes: cover.bytes},
    models: aiBed ? [{role: 'music', id: 'gemini (owner-supplied track)'}] : [],
    costUsd: 0, costEstimated: false,
    credits: [
      {kind: 'music', title: bed.title, creator: aiBed ? 'owner (AI-generated with Gemini)' : bed.artist ?? null, sourceUrl: bed.page ?? null,
        license: aiBed ? 'owner' : bed.license, attribution: null, sha256: bed.sha256},
      ...fonts.map(id => ({kind: 'font', ...FONTS[id], license: 'OFL-1.1', attribution: null, sha256: null})),
      {kind: 'sfx', title: 'Procedural sound effects (engines/motion/tools/make_sfx.py)', creator: 'StudioZero', sourceUrl: null, license: 'owner', attribution: null, sha256: null},
      ...DATA[game],
    ],
    disclosure: aiBed
      ? {aiGenerated: true, aiKinds: ['music'], realisticSynthetic: false, note: 'The music bed is an owner-supplied track made with Gemini; visuals, text and sound effects are not AI-generated.'}
      : {aiGenerated: false, aiKinds: [], realisticSynthetic: false, note: 'Motion graphics from templates; no AI-generated content.'},
  };
}
