/**
 * 后端地址统一出口。
 *
 * 优先级：
 *   1. 环境变量 VITE_API_BASE（在 .env.development 里配置，指向独立域名的后端）
 *   2. 留空 —— 走同源相对路径，由 vite proxy（开发）或 nginx（生产）转发到 5000
 *
 * 为什么默认改成相对路径：
 *   - 内网穿透演示时页面是 https，浏览器不允许它去请求 http://xxx:5000（混合内容）
 *   - 相对路径下局域网和内网穿透都只暴露 5173 一个端口，不用再纠结 5000 通不通
 */
const envBase = import.meta.env.VITE_API_BASE

/**
 * 默认留空 = 走同源相对路径：
 *   - 开发态由 vite.config.js 的 proxy 把 /api、/uploads、/socket.io 转给 127.0.0.1:5000
 *   - 生产态由 nginx 反代到 5000（deploy/nginx.conf.example 已经这么配）
 * 这样局域网和内网穿透都只暴露 5173 一个端口，
 * 也避免 https 页面去请求 http://xxx:5000 被浏览器按混合内容拦掉。
 */
export const API_BASE = envBase || ''

/** SocketIO 与 REST 同源；空值时连当前页面所在的 origin */
export const SOCKET_URL =
  API_BASE || (typeof window !== 'undefined' ? window.location.origin : '')

/** 拼静态资源地址（后端 uploads 下的图片） */
export function uploadUrl(path) {
  if (!path) return ''
  return `${API_BASE}/uploads/${String(path).replace(/\\/g, '/')}`
}
