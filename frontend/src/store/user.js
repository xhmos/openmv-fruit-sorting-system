import { defineStore } from 'pinia'
import { authApi } from '../api'

function readCachedUser() {
  try {
    return JSON.parse(localStorage.getItem('userInfo') || 'null')
  } catch (e) {
    return null
  }
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: readCachedUser(),
  }),

  getters: {
    isLogin: (state) => Boolean(state.token),
    isAdmin: (state) => state.userInfo?.role === 'admin',
    username: (state) => state.userInfo?.username || '',
    roleText: (state) => (state.userInfo?.role === 'admin' ? '管理员' : '操作员'),
  },

  actions: {
    async login(form) {
      const res = await authApi.login(form)
      this.token = res.data.token
      this.userInfo = res.data.user
      localStorage.setItem('token', this.token)
      localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
      return res.data
    },

    async refreshMe() {
      const res = await authApi.me()
      this.userInfo = res.data
      localStorage.setItem('userInfo', JSON.stringify(this.userInfo))
      return res.data
    },

    async logout() {
      try {
        await authApi.logout()
      } catch (e) {
        // 令牌已失效也要清掉本地状态，不能卡在登录态
      }
      this.clear()
    },

    clear() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
    },
  },
})
