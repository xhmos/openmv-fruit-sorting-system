import axios from 'axios'
import { ElMessage } from 'element-plus'
import { API_BASE } from '../config'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
})

// 请求拦截：统一带上 JWT
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：统一拆包 + 统一报错 + 401 跳登录
request.interceptors.response.use(
  (response) => {
    // 文件下载（导出 Excel）不走 code 校验，把完整响应交给调用方
    if (response.config.responseType === 'blob') {
      return response
    }

    const body = response.data
    if (body && body.code !== 0) {
      ElMessage.error(body.msg || '请求失败')
      return Promise.reject(new Error(body.msg || '请求失败'))
    }
    return body
  },
  (error) => {
    const status = error.response?.status
    const body = error.response?.data
    const msg = (body && body.msg) || ''

    if (status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      if (!window.location.hash.startsWith('#/login')) {
        ElMessage.error(msg || '登录已过期，请重新登录')
        window.location.href = `${window.location.origin}/#/login`
      }
    } else if (status === 403) {
      ElMessage.error(msg || '没有权限执行该操作')
    } else if (status === 429) {
      ElMessage.error(msg || '操作过于频繁，请稍后再试')
    } else if (status === 400) {
      ElMessage.error(msg || '参数不合法')
    } else {
      ElMessage.error(msg || '服务异常，请稍后再试')
    }

    return Promise.reject(error)
  }
)

export default request
