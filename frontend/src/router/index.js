import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '../store/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('../layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '实时监控' },
      },
      {
        path: 'record',
        name: 'Record',
        component: () => import('../views/Record.vue'),
        meta: { title: '分拣记录' },
      },
      {
        path: 'setting',
        name: 'Setting',
        component: () => import('../views/Setting.vue'),
        meta: { title: '参数配置' },
      },
      {
        path: 'device',
        name: 'DeviceConnect',
        component: () => import('../views/Device.vue'),
        meta: { title: '设备连接' },
      },
      {
        path: 'user',
        name: 'UserManage',
        component: () => import('../views/UserManage.vue'),
        meta: { title: '用户管理', admin: true },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人中心' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 前端守卫只是挡“误点”，真正的权限判定在后端 admin_required
router.beforeEach((to) => {
  const store = useUserStore()

  if (to.meta.public) {
    if (store.isLogin && to.path === '/login') {
      return { path: '/dashboard' }
    }
    return true
  }

  if (!store.isLogin) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  if (to.meta.admin && !store.isAdmin) {
    return { path: '/dashboard' }
  }

  return true
})

export default router
