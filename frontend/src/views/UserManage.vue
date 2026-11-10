<template>
  <div class="page">
    <el-card shadow="never" class="card">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          placeholder="按用户名搜索"
          clearable
          style="width: 220px"
          @keyup.enter="search"
          @clear="search"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="search">查询</el-button>
        <el-button @click="reset">重置</el-button>

        <div class="toolbar-right">
          <el-button type="primary" @click="openCreate">
            <el-icon class="btn-icon"><Plus /></el-icon>新增用户
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card table-card">
      <el-table v-loading="loading" :data="rows" border stripe row-key="id">
        <el-table-column prop="id" label="ID" width="72" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column label="角色" width="150">
          <template #default="{ row }">
            <el-select
              v-model="row.role"
              size="small"
              :disabled="row.id === myId"
              @change="(value) => changeRole(row, value)"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="操作员" value="operator" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_active"
              :disabled="row.id === myId"
              active-text="启用"
              inactive-text="禁用"
              inline-prompt
              @change="(value) => toggleStatus(row, value)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="create_time" label="创建时间" min-width="165" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openReset(row)">重置密码</el-button>
            <el-button
              link
              type="danger"
              :disabled="row.id === myId"
              @click="removeRow(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="load"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <!-- 新增用户 -->
    <el-dialog v-model="createVisible" title="新增用户" width="440px" @closed="resetCreateForm">
      <el-form ref="createRef" :model="createForm" :rules="createRules" label-width="88px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="3~20 位字母、数字或下划线" />
        </el-form-item>
        <el-form-item label="初始密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="6~64 位" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="操作员（只读查看）" value="operator" />
            <el-option label="管理员（可管理）" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="resetVisible" title="重置密码" width="420px" @closed="resetPwdForm">
      <el-form ref="resetRef" :model="resetForm" :rules="resetRules" label-width="88px">
        <el-form-item label="账号">
          <el-input :model-value="resetTarget?.username" disabled />
        </el-form-item>
        <el-form-item label="新密码" prop="password">
          <el-input v-model="resetForm.password" type="password" show-password placeholder="6~64 位" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="submitReset">重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus } from '@element-plus/icons-vue'
import { userApi } from '../api'
import { useUserStore } from '../store/user'

const store = useUserStore()
const myId = computed(() => store.userInfo?.id)

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const keyword = ref('')
const loading = ref(false)

const createVisible = ref(false)
const creating = ref(false)
const createRef = ref(null)
const createForm = reactive({ username: '', password: '', role: 'operator' })
const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      pattern: /^[A-Za-z0-9_]{3,20}$/,
      message: '只能是 3~20 位字母、数字或下划线',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 6, max: 64, message: '长度需在 6~64 位之间', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

const resetVisible = ref(false)
const resetting = ref(false)
const resetRef = ref(null)
const resetTarget = ref(null)
const resetForm = reactive({ password: '' })
const resetRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 64, message: '长度需在 6~64 位之间', trigger: 'blur' },
  ],
}

async function load() {
  loading.value = true
  try {
    const res = await userApi.list({
      page: page.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    })
    rows.value = (res.data.items || []).map((item) => ({
      ...item,
      is_active: Boolean(item.is_active),
    }))
    total.value = res.data.total || 0
  } catch (e) {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function reset() {
  keyword.value = ''
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

function openCreate() {
  createVisible.value = true
}

function resetCreateForm() {
  createForm.username = ''
  createForm.password = ''
  createForm.role = 'operator'
  createRef.value?.clearValidate()
}

async function submitCreate() {
  if (!createRef.value) return
  try {
    await createRef.value.validate()
  } catch (e) {
    return
  }

  creating.value = true
  try {
    const res = await userApi.create({ ...createForm })
    ElMessage.success(res.msg || '已创建')
    createVisible.value = false
    page.value = 1
    await load()
  } catch (e) {
    // 拦截器已提示（重名 409、用户名格式 400 等）
  } finally {
    creating.value = false
  }
}

function openReset(row) {
  resetTarget.value = row
  resetForm.password = ''
  resetVisible.value = true
}

function resetPwdForm() {
  resetForm.password = ''
  resetRef.value?.clearValidate()
}

async function submitReset() {
  if (!resetRef.value) return
  try {
    await resetRef.value.validate()
  } catch (e) {
    return
  }

  resetting.value = true
  try {
    const res = await userApi.resetPassword(resetTarget.value.id, resetForm.password)
    ElMessage.success(res.msg || '密码已重置')
    resetVisible.value = false
  } catch (e) {
    // 拦截器已提示
  } finally {
    resetting.value = false
  }
}

async function toggleStatus(row, value) {
  try {
    await ElMessageBox.confirm(
      `确定${value ? '启用' : '禁用'}账号「${row.username}」？${value ? '' : '禁用后该账号无法登录。'}`,
      `${value ? '启用' : '禁用'}确认`,
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
  } catch (e) {
    row.is_active = !value
    return
  }

  try {
    await userApi.setStatus(row.id, value)
    ElMessage.success(value ? '已启用' : '已禁用')
  } catch (e) {
    row.is_active = !value // 后端拦截（如最后一个管理员）时回滚开关
  }
}

async function changeRole(row, value) {
  const previous = value === 'admin' ? 'operator' : 'admin'
  try {
    await ElMessageBox.confirm(
      `把「${row.username}」的角色改为${value === 'admin' ? '管理员' : '操作员'}？`,
      '角色变更',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
  } catch (e) {
    row.role = previous
    return
  }

  try {
    await userApi.setRole(row.id, value)
    ElMessage.success('角色已更新')
    await load()
  } catch (e) {
    row.role = previous
  }
}

async function removeRow(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除账号「${row.username}」？该账号的分拣权限将立即失效。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }

  try {
    const res = await userApi.remove(row.id)
    ElMessage.success(res.msg || '已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  border-radius: 10px;
  border: 1px solid var(--app-border);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-right {
  margin-left: auto;
}

.btn-icon {
  margin-right: 4px;
}

.table-card :deep(.el-card__body) {
  padding: 8px 12px 14px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
</style>
