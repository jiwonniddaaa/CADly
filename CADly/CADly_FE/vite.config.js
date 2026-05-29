import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000, // 개발 서버 포트를 3000으로 고정 (선택사항)
  }
})