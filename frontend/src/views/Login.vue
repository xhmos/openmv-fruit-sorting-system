<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <div class="logo">OpenMV</div>
        <h1>果实智能分拣监控管理系统</h1>
        <p>Fruit Sorting Monitor System</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        @keyup.enter="submit"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入账号"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-button type="primary" class="submit-btn" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '../store/user'

const router = useRouter()
const route = useRoute()
const store = useUserStore()

const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: 'admin', password: 'admin123' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

function submit() {
  if (loading.value) return
  formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await store.login({ username: form.username, password: form.password })
      ElMessage.success('登录成功')
      const redirect = route.query.redirect
      router.replace(typeof redirect === 'string' ? redirect : '/dashboard')
    } catch (e) {
      // 错误提示由 axios 拦截器统一处理
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0b3d91 0%, #1677ff 55%, #4d94ff 100%);
  position: relative;
  overflow: hidden;
}

.login-page::before,
.login-page::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.login-page::before {
  width: 520px;
  height: 520px;
  top: -220px;
  right: -120px;
}

.login-page::after {
  width: 360px;
  height: 360px;
  bottom: -180px;
  left: -80px;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 420px;
  padding: 38px 36px 26px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 24px 60px rgba(6, 26, 64, 0.35);
}

.brand {
  text-align: center;
  margin-bottom: 26px;
}

.logo {
  display: inline-block;
  padding: 6px 14px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: var(--el-color-primary);
  color: #fff;
  font-weight: 700;
  letter-spacing: 2px;
}

.brand h1 {
  margin: 0 0 8px;
  font-size: 19px;
  font-weight: 600;
  color: #14233c;
}

.brand p {
  margin: 0;
  font-size: 12px;
  letter-spacing: 1px;
  color: #8a97ab;
}

.submit-btn {
  width: 100%;
  margin-top: 6px;
  height: 44px;
  font-size: 15px;
  letter-spacing: 4px;
}

</style>
