/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: 'var(--font-serif)',
        sans:  'var(--font-sans)',
        mono:  'var(--font-mono)',
      },
      colors: {
        'bg-page':      'var(--color-bg-page)',
        'surface':      'var(--color-surface)',
        'primary':      'var(--color-primary)',
        'ink':          'var(--color-ink)',
        'muted':        'var(--color-muted)',
        'accent':       'var(--color-accent)',
        'danger':       'var(--color-danger)',
        'oxide':        'var(--color-oxide)',
        'teal':         'var(--color-teal)',
        'gold':         'var(--color-gold)',
        'border':       'var(--color-border)',
        'border-dark':  'var(--color-border-dark)',
        'mid-gray':     'var(--color-mid-gray)',
        'paper':        'var(--color-paper)',
        'warm-gray':    'var(--color-warm-gray)',
        'sage':         'var(--color-sage)',
        'sand':         'var(--color-sand)',
        'selection':    'var(--color-selection)',
      },
      borderRadius: {
        DEFAULT: 'var(--radius)',
        chip: 'var(--radius-chip)',
        card: 'var(--radius-card)',
        'card-sm': 'var(--radius-card-sm)',
      },
      boxShadow: {
        'button': '3px 3px 0px 0px var(--color-ink)',
        'soft': 'var(--shadow-soft)',
      },
    },
  },
  plugins: [],
}
