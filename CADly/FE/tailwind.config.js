/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: '#f7f9fb',
        'surface-dim': '#d8dadc',
        primary: '#0f4c81', // Architectural Blue
        'on-primary': '#ffffff',
        secondary: '#555f71',
        outline: '#e2e8f0', // Neutral-200 for 1px borders
        validated: '#d1fae5', // Muted success background
        processing: '#fed7aa', // Muted warning background
      },
      fontFamily: {
        display: ['Metropolis', 'sans-serif'],
        body: ['Hanken Grotesk', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        soft: '4px',
        container: '8px',
        checkbox: '2px',
      },
      boxShadow: {
        'blueprint': '0 10px 20px -10px rgba(0, 0, 0, 0.1)',
      }
    },
  },
  plugins: [],
}