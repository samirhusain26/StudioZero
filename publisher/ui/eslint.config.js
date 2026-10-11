import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'node_modules', 'test-results', 'playwright-report']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.strict,
      reactHooks.configs.flat.recommended,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // Review videos are silent quiz clips without caption tracks; the alt text
      // and every caption are shown as text next to the player.
      'jsx-a11y/media-has-caption': 'off',
      // CSP style-src 'self' blocks inline style attributes; use CSS classes.
      'no-restricted-syntax': ['error', {
        selector: "JSXAttribute[name.name='style']",
        message: 'Inline styles are blocked by the CSP (style-src self). Use a CSS class.',
      }],
    },
  },
])
