import { readFileSync } from 'node:fs';

const themeColors = JSON.parse(readFileSync(new URL('./src/theme-colors.json', import.meta.url), 'utf-8'));

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ...themeColors,
        legal: {
          document: '#0f172a',
          chapter: '#4338ca',
          section: '#0891b2',
          article: '#059669',
          clause: '#d97706',
          point: '#0284c7',
          appendix: '#7c3aed',
        },
      },
      fontFamily: {
        sans: ['Geist', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
