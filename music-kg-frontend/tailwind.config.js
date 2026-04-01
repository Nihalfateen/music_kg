/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'bg-primary':   '#0a0a0a',
        'bg-secondary': '#121212',
        'bg-card':      '#1a1a1a',
        'bg-hover':     '#242424',
        'accent':       '#1db954',
        'accent-hover': '#1ed760',
        'text-primary': '#ffffff',
        'text-secondary':'#b3b3b3',
        'text-muted':   '#535353',
        'border-col':   '#282828',
      },
      fontFamily: {
        sans: ['Syne', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        card: '8px',
        btn:  '4px',
        pill: '50px',
      },
    },
  },
  plugins: [],
}
