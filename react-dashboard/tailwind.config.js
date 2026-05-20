/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        space: {
          bg: '#0a0a1a',
          card: '#0f0f2a',
          border: '#2d1b69',
          accent: '#6d28d9',
          blue: '#1d4ed8',
          muted: '#6b7280',
          text: '#e2e8f0',
          dim: '#94a3b8',
        },
      },
    },
  },
  plugins: [],
}

