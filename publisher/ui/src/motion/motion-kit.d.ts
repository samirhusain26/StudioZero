// The motion kit is typechecked by the motion engine's own tsc (engines/motion/tsconfig.json); the UI only types the
// boundary it uses. Vite resolves @motion/* to engines/motion/src (vite.config.ts).
type MotionEpisodeProps = import('../../../../engines/motion/src/projects/scalargame/types').LibraryEpisodeProps

declare module '@motion/fonts'
declare module '@motion/projects/scalargame/LibraryEpisode' {
  export const LibraryEpisode: import('react').FC<MotionEpisodeProps>
  export const calculateLibraryMetadata: import('remotion').CalculateMetadataFunction<MotionEpisodeProps>
}
declare module '@motion/projects/scalargame/timing' {
  export const FPS: number
}
declare module '@motion/projects/scalargame/types' {
  export type LibraryEpisodeProps = MotionEpisodeProps
}
