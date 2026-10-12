/**
 * The motion engine's Scalargame kit, imported from engines/motion/src (one source of truth with render.sh). Only the
 * lazily loaded Studio motion chunk imports this module, so the other screens stay small.
 */
import '@motion/fonts'
export { LibraryEpisode, calculateLibraryMetadata } from '@motion/projects/scalargame/LibraryEpisode'
export { FPS } from '@motion/projects/scalargame/timing'
export type { LibraryEpisodeProps } from '@motion/projects/scalargame/types'
