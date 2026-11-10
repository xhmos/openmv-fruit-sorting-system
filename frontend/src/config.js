/**
 * 后端地址统一出口。
 *
 * 优先级：
 *   1. 环境变量 VITE_API_BASE（在 .env.development 里配置，用于反代 / 跨机部署）
 *   2. 按当前访问的主机名自动推导 —— 谁访问前端，就指向同一台机器的 5000 端口
 *
 * 这样做的原因：
 *   - 浏览器用 localhost:5173 打开 → 后端 http://localhost:5000
 *   - 用局域网 IP（如 10.153.180.220:5173）在手机/另一台电脑打开 → 后端自动跟着变成
 *     http://10.153.180.220:5000，不需要改任何代码就能给别人演示
 *   - 把原来散在 4 个文件里的硬编码，收敛到这一个地方
 */
const envBase = import.meta.env.VITE_API_BASE

const currentHost =
  (typeof window !== 'undefined' && window.location.hostname) || '127.0.0.1'

export const API_BASE = envBase || `http://${currentHost}:5000`

/** SocketIO 与 REST 同源，跟着 API_BASE 走 */
export const SOCKET_URL = API_BASE

/** 拼静态资源地址（后端 uploads 下的图片） */
export function uploadUrl(path) {
  if (!path) return ''
  return `${API_BASE}/uploads/${String(path).replace(/\\/g, '/')}`
}
