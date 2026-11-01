/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'sans-serif'],
      },
      borderRadius: {
        '3xl': '24px',
        '4xl': '32px',
      },
      colors: {
        background: '#F3F4F6',
        card: '#FFFFFF',
        
                mint: {
          50: '#F0FDF4',
          100: '#DCFCE7',
          400: '#4ADE80',
          600: '#16A34A',
          500: '#22C55E',
          900: '#14532D',
        },
        purple: {
          50: '#F5F3FF',
          100: '#EDE9FE',
          500: '#8B5CF6',
        },
        pastelRed: {
           50: '#FEF2F2',
           100: '#FEE2E2',
           500: '#EF4444',
        },
        charcoal: '#1F2937',
        muted: '#6B7280',
      },
      boxShadow: {
        'soft': '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
        'inner-light': 'inset 0 2px 4px 0 rgba(255, 255, 255, 0.3)',
      }
    },
  },
  plugins: [],
}
