import { io } from 'socket.io-client'
import { SOCKET_URL } from '../config'

let socket = null

/**
 * 全局只保留一个 SocketIO 连接。
 * 握手时后端要求带 JWT（socket.io 的 auth 字段），没带或失效会被直接拒绝连接。
 */
export function getSocket() {
  if (socket) return socket

  const token = localStorage.getItem('token') || ''

  socket = io(SOCKET_URL, {
    // 先 polling 建连、再自动升级到 websocket：
    // 直接优先 websocket 时，若握手被拒，engineio 的 WSGI 驱动会抛 ConnectionError 打 500，
    // 走 polling 则拒绝发生在 HTTP 层，服务端日志干净。
    transports: ['polling', 'websocket'],
    auth: { token },
    reconnection: true,
    reconnectionDelay: 3000,
    reconnectionDelayMax: 10000,
    timeout: 10000,
  })

  // 鉴权被拒（token 缺失/过期/账号被禁用）时不要无限重连，免得刷服务器日志。
  // 服务端拒绝时的文案是 "Connection rejected by server"，这里用正则放宽匹配。
  socket.on('connect_error', (error) => {
    const message = String((error && error.message) || '')
    if (/reject|refus|unauthor/i.test(message)) {
      socket.disconnect()
    }
  })

  return socket
}

export function closeSocket() {
  if (!socket) return
  socket.removeAllListeners()
  socket.disconnect()
  socket = null
}
