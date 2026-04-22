import { defineConfig, searchForWorkspaceRoot } from 'vite'
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
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        path.resolve(__dirname),
        path.resolve(__dirname, '../../packages'),
      ],
    },
  },
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
      '@locales': path.resolve(__dirname, '../../packages/locales'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.split(path.sep).join('/')
          if (!normalizedId.includes('/node_modules/')) {
            return undefined
          }

          const chunkGroups: Array<[string, string[]]> = [
            ['react-vendor', ['/react/', '/react-dom/', '/scheduler/']],
            ['supabase-telegram-vendor', ['/@supabase/', '/@telegram-apps/']],
            ['radix-vendor', ['/@radix-ui/', '/cmdk/', '/vaul/']],
            ['charts-vendor', ['/recharts/', '/d3-']],
            [
              'ui-vendor',
              [
                '/lucide-react/',
                '/class-variance-authority/',
                '/clsx/',
                '/tailwind-merge/',
                '/sonner/',
                '/input-otp/',
                '/react-day-picker/',
                '/date-fns/',
              ],
            ],
            [
              'misc-vendor',
              [
                '/@emotion/',
                '/@mui/',
                '/embla-carousel-react/',
                '/motion/',
                '/next-themes/',
                '/react-dnd/',
                '/react-dnd-html5-backend/',
                '/react-hook-form/',
                '/react-popper/',
                '/react-resizable-panels/',
                '/react-responsive-masonry/',
                '/react-router/',
              ],
            ],
          ]

          for (const [chunkName, matchers] of chunkGroups) {
            if (matchers.some((matcher) => normalizedId.includes(matcher))) {
              return chunkName
            }
          }

          return 'vendor'
        },
      },
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
