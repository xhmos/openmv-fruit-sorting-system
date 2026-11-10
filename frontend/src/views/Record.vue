<template>
  <div class="page">
    <el-card shadow="never" class="card">
      <el-form :inline="true" class="filter-form" @submit.prevent>
        <el-form-item label="品种">
          <el-select
            v-model="query.fruit_type"
            placeholder="全部品种"
            clearable
            filterable
            allow-create
            style="width: 150px"
          >
            <el-option v-for="item in fruitOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>

        <el-form-item label="结果">
          <el-select v-model="query.result" placeholder="全部" clearable style="width: 120px">
            <el-option label="合格" value="good" />
            <el-option label="不合格" value="bad" />
          </el-select>
        </el-form-item>

        <el-form-item label="时间">
          <el-date-picker
            v-model="range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            :default-time="defaultTime"
            style="width: 330px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>

        <div v-if="isAdmin" class="toolbar-right">
          <el-button type="danger" plain :disabled="!selection.length" @click="batchRemove">
            批量删除{{ selection.length ? `(${selection.length})` : '' }}
          </el-button>
          <el-button type="primary" plain :loading="exporting" @click="exportExcel">
            导出 Excel
          </el-button>
        </div>
      </el-form>
    </el-card>

    <el-card shadow="never" class="card table-card">
      <el-table
        v-loading="loading"
        :data="rows"
        border
        stripe
        row-key="id"
        @selection-change="onSelectionChange"
      >
        <el-table-column v-if="isAdmin" type="selection" width="46" />
        <el-table-column prop="id" label="ID" width="72" />

        <el-table-column label="标记图" width="88">
          <template #default="{ row }">
            <el-image
              v-if="row.img_url"
              :src="imgFull(row.img_url)"
              :preview-src-list="[imgFull(row.img_url)]"
              preview-teleported
              fit="cover"
              class="thumb"
            />
            <span v-else class="empty-cell">无</span>
          </template>
        </el-table-column>

        <el-table-column prop="fruit_type" label="品种" min-width="110" />

        <el-table-column label="结果" width="96">
          <template #default="{ row }">
            <el-tag :type="row.result === 'good' ? 'success' : 'danger'" size="small" effect="light">
              {{ row.result === 'good' ? '合格' : '不合格' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="置信度" width="110">
          <template #default="{ row }">{{ (Number(row.confidence) * 100).toFixed(1) }}%</template>
        </el-table-column>

        <el-table-column prop="area" label="像素面积" width="110" sortable />
        <el-table-column prop="create_time" label="分拣时间" min-width="165" sortable />

        <el-table-column v-if="isAdmin" label="操作" width="86" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="load"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { recordApi } from '../api'
import { useUserStore } from '../store/user'
import { API_BASE } from '../config'

const store = useUserStore()
const isAdmin = computed(() => store.isAdmin)

const defaultTime = [new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]

const query = reactive({ fruit_type: '', result: '' })
const range = ref([])
const fruitOptions = ref(['apple', 'orange', 'banana', 'pear', 'tomato', 'grape', 'kiwi', 'mango'])

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const exporting = ref(false)
const selection = ref([])

function imgFull(url) {
  return url ? `${API_BASE}${url}` : ''
}

function buildParams(withPage = true) {
  const params = {}
  if (withPage) {
    params.page = page.value
    params.page_size = pageSize.value
  }
  if (query.fruit_type) params.fruit_type = query.fruit_type
  if (query.result) params.result = query.result
  if (range.value && range.value.length === 2) {
    params.start = range.value[0]
    params.end = range.value[1]
  }
  return params
}

async function load() {
  loading.value = true
  try {
    const res = await recordApi.list(buildParams())
    rows.value = res.data.items || []
    total.value = res.data.total || 0

    // 把本页出现过的品种补进下拉，避免只能选写死的几种
    rows.value.forEach((row) => {
      if (row.fruit_type && !fruitOptions.value.includes(row.fruit_type)) {
        fruitOptions.value.push(row.fruit_type)
      }
    })
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
  query.fruit_type = ''
  query.result = ''
  range.value = []
  page.value = 1
  load()
}

function onSizeChange() {
  page.value = 1
  load()
}

function onSelectionChange(value) {
  selection.value = value
}

async function removeRow(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除第 ${row.id} 条记录（${row.fruit_type}）？图片文件会一起清理。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }

  try {
    await recordApi.remove(row.id)
    ElMessage.success('已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (e) {
    // 拦截器已提示
  }
}

async function batchRemove() {
  if (!selection.value.length) return
  const ids = selection.value.map((row) => row.id)

  try {
    await ElMessageBox.confirm(
      `确定批量删除 ${ids.length} 条记录？不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }

  try {
    const res = await recordApi.batchRemove(ids)
    ElMessage.success(res.msg || '已删除')
    page.value = 1
    await load()
  } catch (e) {
    // 拦截器已提示
  }
}

function stamp() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

async function exportExcel() {
  exporting.value = true
  try {
    const res = await recordApi.exportExcel(buildParams(false))
    const blob = res.data

    // 出错时后端返回的是 JSON，只是被 responseType=blob 包了一层
    if (blob.type && blob.type.indexOf('json') !== -1) {
      const text = await blob.text()
      const body = JSON.parse(text)
      ElMessage.error(body.msg || '导出失败')
      return
    }

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sort_record_${stamp()}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    ElMessage.success('报表已导出')
  } catch (e) {
    // 拦截器已提示
  } finally {
    exporting.value = false
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

.filter-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 0;
}

.filter-form :deep(.el-form-item) {
  margin-bottom: 8px;
  margin-right: 16px;
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  gap: 8px;
  padding-bottom: 8px;
}

.table-card :deep(.el-card__body) {
  padding: 8px 12px 14px;
}

.thumb {
  width: 52px;
  height: 40px;
  border-radius: 4px;
  background: #f2f6fc;
}

.empty-cell {
  color: #b5c0cf;
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}
</style>
