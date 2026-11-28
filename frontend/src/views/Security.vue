<template>
  <div class="page">
    <!-- ---------- 顶部：周期选择 + 四个指标 ---------- -->
    <el-card shadow="never" class="card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="section-title">安全中心</span>
          <el-tag size="small" type="info" effect="plain">
            记录外部尝试攻击的方式、次数与来源
          </el-tag>
        </div>
        <div class="toolbar-right">
          <el-radio-group v-model="days" size="small" @change="reload">
            <el-radio-button :value="1">近 24 小时</el-radio-button>
            <el-radio-button :value="7">近 7 天</el-radio-button>
            <el-radio-button :value="30">近 30 天</el-radio-button>
            <el-radio-button :value="90">近 90 天</el-radio-button>
          </el-radio-group>
          <el-button size="small" :loading="loading" @click="reload">
            <el-icon class="btn-icon"><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat">
          <div class="stat-label">今日尝试攻击</div>
          <div class="stat-value">{{ overview.summary.today_total || 0 }}<span class="unit">次</span></div>
          <div class="stat-sub">
            {{ overview.summary.today_events || 0 }} 条记录 ·
            {{ overview.summary.today_ips || 0 }} 个来源 IP
          </div>
        </div>
        <div class="stat">
          <div class="stat-label">今日高危尝试</div>
          <div class="stat-value danger">{{ overview.summary.today_high || 0 }}<span class="unit">次</span></div>
          <div class="stat-sub">注入 / 穿越 / 撞密码 等</div>
        </div>
        <div class="stat">
          <div class="stat-label">被挡下的请求</div>
          <div class="stat-value">{{ overview.summary.blocked || 0 }}<span class="unit">次</span></div>
          <div class="stat-sub">401 / 403 / 429，均未得手</div>
        </div>
        <div class="stat">
          <div class="stat-label">网关层拦截（今日）</div>
          <div class="stat-value">{{ overview.summary.gateway_blocked || 0 }}<span class="unit">次</span></div>
          <div class="stat-sub">Nginx 直接拒掉的穿越 / 畸形请求</div>
        </div>
      </div>
    </el-card>

    <!-- ---------- 趋势 + 攻击方式 ---------- -->
    <div class="row">
      <el-card shadow="never" class="card chart-card">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">攻击尝试趋势</span>
            <span class="panel-sub">蓝色为总尝试，红色为高危</span>
          </div>
        </template>
        <div ref="trendRef" class="chart"></div>
      </el-card>

      <el-card shadow="never" class="card chart-card">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">攻击方式分布</span>
            <span class="panel-sub">按次数统计</span>
          </div>
        </template>
        <div ref="typeRef" class="chart"></div>
      </el-card>
    </div>

    <!-- ---------- 来源 IP + 安全体检 ---------- -->
    <div class="row">
      <el-card shadow="never" class="card">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">来源 IP（{{ periodText }}）</span>
            <span class="panel-sub">点 IP 可筛选下面的明细</span>
          </div>
        </template>
        <el-table :data="overview.top_ips" size="small" border stripe empty-text="这段时间没有外部尝试">
          <el-table-column prop="ip" label="来源 IP" min-width="130">
            <template #default="{ row }">
              <el-button link type="primary" @click="filterByIp(row.ip)">{{ row.ip }}</el-button>
            </template>
          </el-table-column>
          <el-table-column prop="count" label="次数" width="80" align="center" />
          <el-table-column label="主要方式" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="t in row.types"
                :key="t"
                size="small"
                effect="plain"
                class="type-tag"
              >
                {{ t }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="last_time" label="最近一次" min-width="160" />
        </el-table>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">安全体检</span>
            <span class="panel-sub">
              风险 {{ checklist.failed || 0 }} 项 · 待确认 {{ checklist.unknown || 0 }} 项
            </span>
          </div>
        </template>
        <div v-loading="checklistLoading" class="check-list">
          <div v-for="item in checklist.items" :key="item.key" class="check-item">
            <el-tag
              size="small"
              :type="item.ok === true ? 'success' : item.ok === false ? 'danger' : 'info'"
              effect="dark"
              class="check-tag"
            >
              {{ item.ok === true ? '通过' : item.ok === false ? '风险' : '待确认' }}
            </el-tag>
            <div class="check-body">
              <div class="check-name">{{ item.name }}</div>
              <div class="check-detail">{{ item.detail }}</div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- ---------- 明细 ---------- -->
    <el-card shadow="never" class="card">
      <div class="toolbar">
        <div class="toolbar-left filters">
          <el-select v-model="filters.type" placeholder="全部方式" clearable size="small" style="width: 170px" @change="search">
            <el-option v-for="t in typeOptions" :key="t.type" :label="t.label" :value="t.type" />
          </el-select>
          <el-select v-model="filters.severity" placeholder="全部级别" clearable size="small" style="width: 120px" @change="search">
            <el-option label="高危" value="high" />
            <el-option label="中危" value="medium" />
            <el-option label="低危" value="low" />
          </el-select>
          <el-input
            v-model="filters.keyword"
            placeholder="按路径关键字搜索"
            clearable
            size="small"
            style="width: 200px"
            @keyup.enter="search"
            @clear="search"
          />
          <el-button size="small" type="primary" @click="search">查询</el-button>
          <el-button size="small" @click="resetFilters">重置</el-button>
          <el-tag v-if="filters.ip" size="small" closable @close="clearIp">
            IP：{{ filters.ip }}
          </el-tag>
        </div>
        <div class="toolbar-right">
          <el-button size="small" :loading="purging" @click="purge">
            <el-icon class="btn-icon"><Delete /></el-icon>清理 90 天前记录
          </el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="rows" border stripe empty-text="没有匹配的攻击记录">
        <el-table-column prop="last_time" label="最近时间" width="160" />
        <el-table-column label="攻击方式" width="150">
          <template #default="{ row }">
            <el-tag :type="severityType(row.severity)" size="small" effect="light">
              {{ row.type_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="80" align="center">
          <template #default="{ row }">
            <span :class="'sev sev-' + row.severity">{{ severityText(row.severity) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="来源 IP" width="140" show-overflow-tooltip />
        <el-table-column prop="method" label="方法" width="80" align="center" />
        <el-table-column label="请求路径" min-width="230">
          <template #default="{ row }">
            <el-tooltip :content="row.path || '-'" placement="top" :show-after="300">
              <span class="path-text">{{ row.path || '-' }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="status_code" label="响应码" width="80" align="center" />
        <el-table-column prop="count" label="次数" width="70" align="center" />
        <el-table-column prop="detail" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="loadEvents"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <div class="footnote">
      记录从本功能部署后开始积累；同一来源、同一方式、同一路径在 60 秒内会合并成一条并累计次数。
      明细里只保存「哪个参数命中了哪类特征」，不回显攻击载荷原文。
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Delete } from '@element-plus/icons-vue'
import * as echarts from 'echarts/core'
import { LineChart, PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { securityApi } from '../api'

echarts.use([LineChart, PieChart, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const days = ref(7)
const loading = ref(false)
const checklistLoading = ref(false)
const purging = ref(false)

const overview = reactive({
  summary: {},
  trend: { labels: [], total: [], high: [] },
  types: [],
  top_ips: [],
})

const checklist = reactive({ items: [], failed: 0, unknown: 0 })

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ type: '', severity: '', keyword: '', ip: '' })
const typeOptions = ref([])

const periodText = computed(() => {
  const map = { 1: '近 24 小时', 7: '近 7 天', 30: '近 30 天', 90: '近 90 天' }
  return map[days.value] || ''
})

const trendRef = ref(null)
const typeRef = ref(null)
let trendChart = null
let typeChart = null

function severityType(sev) {
  return sev === 'high' ? 'danger' : sev === 'medium' ? 'warning' : 'info'
}
function severityText(sev) {
  return sev === 'high' ? '高危' : sev === 'medium' ? '中危' : '低危'
}

// ---------------------------------------------------------------- 数据加载
async function loadOverview() {
  loading.value = true
  try {
    const res = await securityApi.overview(days.value)
    const data = res.data || {}
    Object.assign(overview.summary, data.summary || {})
    Object.assign(overview.trend, data.trend || {})
    overview.types = data.types || []
    overview.top_ips = data.top_ips || []
    await nextTick()
    renderTrend()
    renderTypes()
  } catch (e) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function loadEvents() {
  loading.value = true
  try {
    const res = await securityApi.events({
      page: page.value,
      page_size: pageSize.value,
      days: days.value,
      type: filters.type || undefined,
      severity: filters.severity || undefined,
      ip: filters.ip || undefined,
      keyword: filters.keyword || undefined,
    })
    const data = res.data || {}
    rows.value = data.items || []
    total.value = data.total || 0
    if (data.types) typeOptions.value = data.types
  } catch (e) {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadChecklist() {
  checklistLoading.value = true
  try {
    const res = await securityApi.checklist()
    const data = res.data || {}
    checklist.items = data.items || []
    checklist.failed = data.failed || 0
    checklist.unknown = data.unknown || 0
  } catch (e) {
    // 拦截器已提示
  } finally {
    checklistLoading.value = false
  }
}

function reload() {
  page.value = 1
  loadOverview()
  loadEvents()
  loadChecklist()
}

function search() {
  page.value = 1
  loadEvents()
}

function onSizeChange() {
  page.value = 1
  loadEvents()
}

function resetFilters() {
  filters.type = ''
  filters.severity = ''
  filters.keyword = ''
  filters.ip = ''
  search()
}

function filterByIp(ip) {
  filters.ip = ip
  page.value = 1
  loadEvents()
}

function clearIp() {
  filters.ip = ''
  search()
}

async function purge() {
  try {
    await ElMessageBox.confirm(
      '只会删除 90 天前的历史记录，最近的分析数据不受影响。确定继续？',
      '清理安全记录',
      { type: 'warning', confirmButtonText: '清理', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }
  purging.value = true
  try {
    const res = await securityApi.purge(90)
    ElMessage.success(res.msg || '已清理')
    reload()
  } catch (e) {
    // 拦截器已提示
  } finally {
    purging.value = false
  }
}

// ---------------------------------------------------------------- 图表
function renderTrend() {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['总尝试', '高危'], right: 10, top: 0, itemWidth: 12, itemHeight: 8 },
    grid: { left: 40, right: 16, top: 36, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: overview.trend.labels || [],
      axisLabel: { fontSize: 11, color: '#7a8699' },
      axisLine: { lineStyle: { color: '#e4e9f2' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { fontSize: 11, color: '#7a8699' },
      splitLine: { lineStyle: { color: '#eef1f7' } },
    },
    series: [
      {
        name: '总尝试',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: overview.trend.total || [],
        lineStyle: { width: 2, color: '#2f6bff' },
        itemStyle: { color: '#2f6bff' },
        areaStyle: { opacity: 0.08, color: '#2f6bff' },
      },
      {
        name: '高危',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: overview.trend.high || [],
        lineStyle: { width: 2, color: '#e5484d' },
        itemStyle: { color: '#e5484d' },
      },
    ],
  })
}

function renderTypes() {
  if (!typeRef.value) return
  if (!typeChart) typeChart = echarts.init(typeRef.value)
  const data = (overview.types || []).map((t) => ({ name: t.label, value: t.count }))
  typeChart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 次（{d}%）' },
    legend: {
      type: 'scroll',
      bottom: 0,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { fontSize: 11, color: '#5a6474' },
    },
    color: ['#2f6bff', '#e5484d', '#f5a524', '#17b26a', '#7a5af8', '#12b5cb', '#98a2b3'],
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data: data.length ? data : [{ name: '暂无数据', value: 1 }],
      },
    ],
  })
}

function onResize() {
  trendChart && trendChart.resize()
  typeChart && typeChart.resize()
}

onMounted(() => {
  reload()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  trendChart && trendChart.dispose()
  typeChart && typeChart.dispose()
  trendChart = null
  typeChart = null
})
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
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filters {
  flex-wrap: wrap;
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
}

.btn-icon {
  margin-right: 4px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.stat {
  background: var(--el-fill-color-lighter, #f7f9fc);
  border-radius: 10px;
  padding: 14px 16px;
}

.stat-label {
  font-size: 12px;
  color: var(--app-text-sub, #7a8699);
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.3;
  margin: 4px 0;
  color: var(--app-text, #1f2937);
}

.stat-value.danger {
  color: #e5484d;
}

.unit {
  font-size: 12px;
  font-weight: 400;
  margin-left: 4px;
  color: var(--app-text-sub, #7a8699);
}

.stat-sub {
  font-size: 12px;
  color: var(--app-text-sub, #7a8699);
}

.row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
}

.panel-sub {
  font-size: 12px;
  color: var(--app-text-sub, #7a8699);
}

.chart-card :deep(.el-card__body) {
  padding: 8px 10px 12px;
}

.chart {
  height: 250px;
}

.check-list {
  max-height: 292px;
  overflow-y: auto;
  padding-right: 4px;
}

.check-item {
  display: flex;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px dashed var(--app-border, #e8edf5);
}

.check-item:last-child {
  border-bottom: none;
}

.check-tag {
  flex: 0 0 auto;
  margin-top: 1px;
}

.check-body {
  min-width: 0;
}

.check-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text, #1f2937);
}

.check-detail {
  font-size: 12px;
  color: var(--app-text-sub, #7a8699);
  line-height: 1.45;
  word-break: break-all;
}

.type-tag {
  margin: 2px 4px 2px 0;
}

.sev {
  font-size: 12px;
  font-weight: 600;
}

.sev-high {
  color: #e5484d;
}

.sev-medium {
  color: #f5a524;
}

.sev-low {
  color: #98a2b3;
}

.path-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.footnote {
  font-size: 12px;
  color: var(--app-text-sub, #7a8699);
  line-height: 1.6;
  padding: 0 4px 8px;
}

@media (max-width: 1200px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stat-grid {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .toolbar-right {
    margin-left: 0;
    width: 100%;
    justify-content: flex-end;
  }

  .chart {
    height: 210px;
  }
}
</style>
