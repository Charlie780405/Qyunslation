import qyunsappsPreset from './src/next/vendor/tw3-preset.cjs'; // QyunsApps 生成的品牌色阶与语义色（不手改）

/** @type {import('tailwindcss').Config} */
export default {
  presets: [qyunsappsPreset],
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#0066cc',
          hover: '#0052a3',
        },
        success: '#198754',
        danger: '#dc3545',
        warning: '#ffc107',
        info: '#0dcaf0',
      }
    }
  },
  plugins: [],
}
