import request from './request'

// 认证
export const authApi = {
  login: (data) => request.post('/api/auth/login', data),
  me: () => request.get('/api/auth/me'),
  logout: () => request.post('/api/auth/logout'),
  // 头像：FormData 里字段名必须是 file；不要手动设 Content-Type，让浏览器自己带 boundary
  uploadAvatar: (formData) => request.post('/api/auth/avatar', formData, { timeout: 30000 }),
  resetAvatar: () => request.delete('/api/auth/avatar'),
}

// 分拣记录
export const recordApi = {
  list: (params) => request.get('/api/record/list', { params }),
  stats: (days = 7) => request.get('/api/record/stats', { params: { days } }),
  remove: (id) => request.delete(`/api/record/${id}`),
  batchRemove: (ids) => request.post('/api/record/batch-delete', { ids }),
  exportExcel: (params) => request.get('/api/record/export', { params, responseType: 'blob' }),
}

// 识别参数
export const settingApi = {
  list: () => request.get('/api/setting/list'),
  update: (settings) => request.put('/api/setting/update', { settings }),
}

// 用户管理（除 list 外都要求管理员）
export const userApi = {
  list: (params) => request.get('/api/user/list', { params }),
  create: (data) => request.post('/api/user/create', data),
  setStatus: (id, isActive) => request.put(`/api/user/${id}/status`, { is_active: isActive }),
  resetPassword: (id, password) => request.put(`/api/user/${id}/password`, { password }),
  setRole: (id, role) => request.put(`/api/user/${id}/role`, { role }),
  remove: (id) => request.delete(`/api/user/${id}`),
}

// 系统设备识别（摄像头 / 串口清单）与「我的设备」
export const systemApi = {
  // 扫描要起 PowerShell 枚举 PnP 设备，实测约 4 秒、机器忙时更久，
  // 所以单独把超时放宽到 60 秒，避免被 axios 默认的 15 秒掐断后报「服务异常」
  devices: (force = false) =>
    request.get('/api/system/devices', {
      params: { force: force ? 1 : 0 },
      timeout: 60000,
    }),

  // 已保存设备（增删改连要求管理员，列表只要求登录）
  // 新增/连接这两个动作会在后端触发一次设备探测（缓存没命中时等于一次扫描），同样放宽超时
  savedList: () => request.get('/api/system/saved'),
  saveDevice: (data) => request.post('/api/system/saved', data, { timeout: 60000 }),
  removeDevice: (id) => request.delete(`/api/system/saved/${id}`),
  connectDevice: (id) =>
    request.post(`/api/system/saved/${id}/connect`, null, { timeout: 60000 }),
  toggleAuto: (id, autoConnect) =>
    request.patch(`/api/system/saved/${id}`, { auto_connect: autoConnect }),

  // 探测未知设备：只测能不能连，不写库
  probe: (devType, target) =>
    request.post('/api/system/probe', { dev_type: devType, target }, { timeout: 30000 }),
}

// 摄像头采集服务（后端直连摄像头，画面只在内存里流转，不落盘）
export const deviceApi = {
  // 只是一次内存状态读取，很快
  cameraStatus: () => request.get('/api/device/camera/status'),
  // 启动要真的打开摄像头，被占用或驱动初始化慢时可能要几秒，放宽到 30 秒
  startCamera: (data = {}) =>
    request.post('/api/device/camera/start', data, { timeout: 30000 }),
  stopCamera: () => request.post('/api/device/camera/stop', {}, { timeout: 20000 }),
  // 运行中切开关：detect / snapshot / record 互相独立
  cameraConfig: (data) => request.patch('/api/device/camera/config', data),

  // 录像文件：直接扫 uploads/videos 目录，没有单独建表
  videoList: () => request.get('/api/device/videos'),
  deleteVideo: (name) => request.delete(`/api/device/videos/${encodeURIComponent(name)}`),
}
