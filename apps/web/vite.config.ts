import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

const extraAllowedHosts = (process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean)

export default defineConfig({
  plugins: [
    // The React and Tailwind plugins are both required for Make, even if
    // Tailwind is not being actively used – do not remove them
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    host: true,
    allowedHosts: ['relentlessly-logical-turaco.cloudpub.ru', ...extraAllowedHosts],
    fs: {
      allow: [path.resolve(__dirname, '../../packages')],
    },
  },
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
      '@locales': path.resolve(__dirname, '../../packages/locales'),
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
