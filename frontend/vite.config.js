import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 前端只发相对路径，统一由 vite 转给本机后端。
// 好处：局域网和内网穿透都只需要暴露一个端口，
// 也不会出现 https 页面去请求 http://xxx:5000 被浏览器按混合内容拦掉。
const PROXY = {
  '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true, ws: true },
  '/uploads': { target: 'http://127.0.0.1:5000', changeOrigin: true },
  '/socket.io': { target: 'http://127.0.0.1:5000', changeOrigin: true, ws: true },
}

// 内网穿透的域名每次随机，按后缀放行 trycloudflare 的子域。
// Vite 6 以后对陌生 Host 头会直接返回 403，不加这行穿透进来就是白页。
const ALLOWED_HOSTS = ['.trycloudflare.com', '.cpolar.top', '.cpolar.cn']

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: ALLOWED_HOSTS,
    proxy: PROXY,
  },
  // 对外演示走这里：先在 dist 里打包好，再用 preview 以静态方式跑。
  // 产物只有几个 js/css，手机不会再像 dev 模式那样逐个拉上百个模块，
  // 也就不会因为单个模块超时被取消导致白屏。
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: ALLOWED_HOSTS,
    proxy: PROXY,
  },
})
