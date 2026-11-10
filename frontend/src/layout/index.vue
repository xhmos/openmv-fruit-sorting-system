<template>
  <div class="layout">
    <aside class="sidebar" :class="{ collapsed }">
      <div class="brand">
        <span class="brand-mark">F</span>
        <span v-show="!collapsed" class="brand-text">果实分拣监控</span>
      </div>

      <el-menu
        :default-active="activePath"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        class="side-menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Monitor /></el-icon>
          <template #title>实时监控</template>
        </el-menu-item>
        <el-menu-item index="/record">
          <el-icon><Tickets /></el-icon>
          <template #title>分拣记录</template>
        </el-menu-item>
        <el-menu-item index="/setting">
          <el-icon><SetUp /></el-icon>
          <template #title>参数配置</template>
        </el-menu-item>
        <el-menu-item index="/device">
          <el-icon><Connection /></el-icon>
          <template #title>设备连接</template>
        </el-menu-item>
        <el-menu-item v-if="store.isAdmin" index="/user">
          <el-icon><UserFilled /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>
          <template #title>个人中心</template>
        </el-menu-item>
      </el-menu>

      <div v-show="!collapsed" class="version">OpenMV · ESP32</div>
    </aside>

    <section class="main">
      <header class="topbar">
        <div class="topbar-left">
          <el-button text class="collapse-btn" @click="collapsed = !collapsed">
            <el-icon><Expand v-if="collapsed" /><Fold v-else /></el-icon>
          </el-button>
          <span class="page-title">{{ route.meta.title }}</span>
        </div>

        <div class="topbar-right">
          <el-tag :type="store.isAdmin ? 'primary' : 'info'" effect="light" size="small">
            {{ store.roleText }}
          </el-tag>
          <el-dropdown trigger="click" @command="onCommand">
            <span class="user-name">
              <el-avatar :size="24" :src="avatarSrc" class="user-avatar">
                {{ initial }}
              </el-avatar>
              {{ store.username }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <router-view />
      </main>
    </section>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Monitor,
  Tickets,
  SetUp,
  Connection,
  UserFilled,
  User,
  Fold,
  Expand,
  ArrowDown,
} from '@element-plus/icons-vue'
import { useUserStore } from '../store/user'
import { uploadUrl } from '../config'

const route = useRoute()
const router = useRouter()
const store = useUserStore()

// 顶部也显示头像，没传过就回到账号首字母
const avatarSrc = computed(() => {
  const p = store.userInfo?.avatar
  return p ? uploadUrl(p) : ''
})
const initial = computed(() => (store.username || '?').slice(0, 1).toUpperCase())

const collapsed = ref(false)
const activePath = computed(() => route.path)

async function onCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
    return
  }
  if (command !== 'logout') return
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      type: 'warning',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
  } catch (e) {
    return
  }
  await store.logout()
  ElMessage.success('已退出登录')
  router.replace('/login')
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100%;
}

.sidebar {
  width: 220px;
  flex: 0 0 220px;
  background: var(--app-sidebar);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease, flex-basis 0.2s ease;
  overflow: hidden;
}

.sidebar.collapsed {
  width: 64px;
  flex-basis: 64px;
}

.brand {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  color: #ffffff;
  flex: 0 0 60px;
}

.brand-mark {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  border-radius: 8px;
  background: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
}

.brand-text {
  font-size: 15px;
  letter-spacing: 1px;
  white-space: nowrap;
}

.side-menu {
  border-right: none;
  background: transparent;
  flex: 1;
  overflow-y: auto;
}

.side-menu:not(.el-menu--collapse) {
  width: 220px;
}

.version {
  padding: 14px 18px;
  font-size: 12px;
  color: rgba(199, 214, 234, 0.65);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: 60px;
  flex: 0 0 60px;
  background: #ffffff;
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: var(--app-shadow);
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-btn {
  font-size: 18px;
  color: var(--app-text-sub);
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: var(--app-text);
  outline: none;
}

.user-avatar {
  margin-right: 4px;
  font-size: 13px;
  font-weight: 600;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
</style>
