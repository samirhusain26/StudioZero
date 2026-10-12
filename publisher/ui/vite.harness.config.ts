import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { MOTION_RESOLVE } from './vite.config'

// Dev only: `vite --config vite.harness.config.ts` serves motion-harness/ with the motion engine's public/ as the
// static root (what staticFile() resolves against). Never used by build or build:static.
export default defineConfig({
  root: 'motion-harness',
  publicDir: '../../../engines/motion/public',
  plugins: [react()],
  resolve: MOTION_RESOLVE,
  server: { port: 5199, strictPort: true, fs: { allow: ['..', '../../../engines/motion'] } },
})
