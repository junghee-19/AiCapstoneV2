/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 도메인 — PASS/FAIL 표시
        pass: '#22c55e',
        fail: '#ef4444',

        // SnowUI 디자인 토큰 — 흰 배경 + 검정 알파 텍스트 + 파스텔 카드
        'Background-1': '#FFFFFF',
        'Black-100%':   '#1C1C1C',
        'Black-80%':    'rgba(28, 28, 28, 0.8)',
        'Black-40%':    'rgba(28, 28, 28, 0.4)',
        'Black-20%':    'rgba(28, 28, 28, 0.2)',
        'Black-10%':    'rgba(28, 28, 28, 0.1)',
        'Black-4%':     'rgba(28, 28, 28, 0.04)',
        'White-10%':    'rgba(255, 255, 255, 0.1)',

        // 카드 배경 (파스텔)
        'Color-1':      '#E5ECF6',   // 연파랑 — 정보·통계 카드
        'Color-2':      '#E3F5FF',   // 연시안 — 보조 카드
        'Color-3':      '#FFF4E5',   // 연주황 — 경고
        'Color-4':      '#F0F9E8',   // 연녹 — 성공

        // 로고
        'Logo-1':       '#1C1C1C',
        'Logo-2':       '#1C1C1C',
      },
    },
  },
  plugins: [],
}
