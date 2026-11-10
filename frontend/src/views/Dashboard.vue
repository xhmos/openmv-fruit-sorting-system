<template>
  <div class="dashboard">
    <div class="top-row">
      <el-card class="panel video-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">实时分拣画面</span>
            <div class="panel-head-right">
              <el-radio-group v-model="camMode" size="small" @change="onModeChange">
                <el-radio-button value="camera">摄像头直连</el-radio-button>
                <el-radio-button value="device">设备上报</el-radio-button>
              </el-radio-group>
              <el-tag :type="socketOnline ? 'success' : 'info'" size="small" effect="dark">
                {{ socketOnline ? '实时推送已连接' : '推送未连接' }}
              </el-tag>
              <el-button text size="small" @click="reloadStream">重连画面</el-button>
            </div>
          </div>
        </template>

        <div class="video-wrap">
          <img
            v-if="streamUrl && !imageError"
            :src="streamUrl"
            class="video"
            alt="实时画面"
            @error="imageError = true"
          />
          <div v-else class="video-placeholder">
            <el-icon class="ph-icon"><VideoCamera /></el-icon>
            <p v-if="imageError">画面加载失败，点右上角「重连画面」</p>
            <p v-else-if="camMode === 'camera' && !camStatus.running">摄像头采集未启动，点下方「启动采集」</p>
            <p v-else>暂无实时画面</p>
            <span v-if="camMode === 'device'">等待 OpenMV 通过 /api/device/frame 上传实时帧</span>
            <span v-else>画面只在内存里流转，不落盘；只有识别到果实才会截图存档</span>
          </div>

          <div class="video-meta">
            <span v-if="camMode === 'camera'">
              已读 {{ camStatus.frames || 0 }} 帧 · {{ camStatus.fps || 0 }} fps
            </span>
            <span v-else>最近帧：{{ lastFrameText }}</span>
            <span v-if="latest">
              最新判别：{{ latest.fruit_type }} ·
              <b :class="latest.result === 'good' ? 'ok' : 'bad'">
                {{ latest.result === 'good' ? '合格' : '不合格' }}
              </b>
            </span>
          </div>
        </div>

        <!-- 采集控制条：只在摄像头直连模式下出现 -->
        <div v-if="camMode === 'camera'" class="cam-bar">
          <div class="cam-line">
            <el-tag :type="camStatus.running ? 'success' : 'info'" size="small" effect="dark">
              {{ camStatus.running ? '采集运行中' : '采集未启动' }}
            </el-tag>
            <span v-if="camStatus.running" class="cam-text">
              {{ camStatus.width }}×{{ camStatus.height }} · {{ camStatus.source }}
            </span>
            <span v-else class="cam-text">由后端直接打开摄像头，适合没有 OpenMV 板子时演示</span>
            <span v-if="camStatus.error" class="cam-text cam-err">{{ camStatus.error }}</span>
          </div>

          <div class="cam-line">
            <el-button
              size="small"
              type="primary"
              :loading="camLoading"
              :disabled="!isAdmin || camStatus.running"
              @click="startCamera"
            >
              启动采集
            </el-button>
            <el-button
              size="small"
              :disabled="!isAdmin || !camStatus.running"
              @click="stopCamera"
            >
              停止采集
            </el-button>

            <span class="cam-sep"></span>

            <span class="cam-label">识别</span>
            <el-switch
              v-model="switches.detect"
              size="small"
              :disabled="!isAdmin || !camStatus.running"
              @change="(v) => patchSwitch('detect', v)"
            />
            <span class="cam-label">命中存图</span>
            <el-switch
              v-model="switches.snapshot"
              size="small"
              :disabled="!isAdmin || !camStatus.running"
              @change="(v) => patchSwitch('snapshot', v)"
            />
            <span class="cam-label">录像</span>
            <el-switch
              v-model="switches.record"
              size="small"
              :disabled="!isAdmin || !camStatus.running || !camStatus.video_supported"
              @change="(v) => patchSwitch('record', v)"
            />
            <span v-if="!isAdmin" class="cam-hint">操作员只能看，启停与开关需要管理员</span>
            <span v-else-if="!camStatus.video_supported" class="cam-hint">
              当前 opencv 写不了 mp4，录像暂不可用
            </span>
          </div>

          <div v-if="camStatus.running" class="cam-line">
            <span class="cam-text">
              命中 {{ camStatus.hits }} 次 · 存图 {{ camStatus.snapshots }} 张 · 录像 {{ camStatus.videos }} 段
            </span>
            <span class="cam-text">门槛：置信度 ≥ {{ camStatus.min_confidence }}、最小面积 {{ camStatus.min_area }} px</span>
            <span v-if="camStatus.last_hit" class="cam-text">最近命中 {{ camStatus.last_hit }}</span>
          </div>

          <div class="cam-line">
            <span class="cam-hint">
              颜色阈值是演示值，对着人脸或桌面会误判（常见是判成桃子/芒果）；要准就对着真实果实调参数页的 H/S/V
            </span>
          </div>
        </div>

        <!-- 录像文件：只存在硬盘上，库里不记录，所以这里直接扫目录 -->
        <div v-if="camMode === 'camera'" class="video-box">
          <div class="video-head">
            <span class="video-title">录像文件</span>
            <span class="cam-hint">在 backend\uploads\videos\ 下，删了就没了</span>
            <el-button size="small" text type="primary" @click="loadVideos">刷新</el-button>
          </div>

          <div v-if="!videos.length" class="cam-hint video-empty">
            还没有录像。打开上方「录像」开关，识别到果实时会自动存一段（命中前约 3 秒 + 之后 2 秒）。
          </div>

          <div v-for="v in videos" :key="v.name" class="video-row">
            <span class="video-name" :title="v.name">{{ v.name }}</span>
            <span class="video-meta">{{ v.size_text }} · {{ v.create_time }}</span>
            <el-button link type="primary" size="small" @click="playVideo(v)">播放</el-button>
            <el-button link type="danger" size="small" :disabled="!isAdmin" @click="removeVideo(v)">
              删除
            </el-button>
          </div>
        </div>
      </el-card>

      <div class="stat-col">
        <el-card v-for="item in statCards" :key="item.key" class="stat-card" shadow="never">
          <div class="stat-label">{{ item.label }}</div>
          <div class="stat-value" :style="{ color: item.color }">{{ item.value }}</div>
          <div class="stat-foot">{{ item.foot }}</div>
        </el-card>
      </div>
    </div>

    <div class="bottom-row">
      <el-card class="panel chart-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">分拣趋势与良品率</span>
            <el-radio-group v-model="days" size="small" @change="loadStats">
              <el-radio-button :value="1">今日</el-radio-button>
              <el-radio-button :value="7">近 7 天</el-radio-button>
            </el-radio-group>
          </div>
        </template>
        <div ref="chartRef" class="chart"></div>
      </el-card>

      <el-card class="panel list-panel" shadow="never">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">最近分拣</span>
            <el-button text size="small" @click="goRecord">查看全部</el-button>
          </div>
        </template>

        <div class="recent-list">
          <div v-for="row in recent" :key="row.id" class="recent-item">
            <div class="recent-main">
              <span class="fruit">{{ row.fruit_type }}</span>
              <el-tag
                :type="row.result === 'good' ? 'success' : 'danger'"
                size="small"
                effect="light"
              >
                {{ row.result === 'good' ? '合格' : '不合格' }}
              </el-tag>
            </div>
            <div class="recent-meta">
              <span>{{ Math.round(row.confidence * 1000) / 10 }}%</span>
              <span>{{ row.area }} px</span>
              <span>{{ shortTime(row.create_time) }}</span>
            </div>
          </div>
          <el-empty v-if="!recent.length" description="暂无分拣记录" :image-size="70" />
        </div>
      </el-card>
    </div>

    <!-- 录像预览：直接放后端 /uploads/videos 下的 mp4 -->
    <el-dialog
      v-model="videoDialog"
      :title="playing?.name || '录像预览'"
      width="720px"
      destroy-on-close
    >
      <video
        v-if="playing"
        :src="playing.fullUrl"
        controls
        autoplay
        class="video-player"
      ></video>
      <p v-if="playing" class="cam-hint video-dialog-tip">
        {{ playing.size_text }} · {{ playing.create_time }} · 打不开就说明浏览器缺 mp4 解码器，用本地播放器打开这个文件
      </p>
      <template #footer>
        <el-button @click="videoDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoCamera } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { recordApi, deviceApi } from '../api'
import { getSocket, closeSocket } from '../utils/socket'
import { useUserStore } from '../store/user'
import { API_BASE } from '../config'

const store = useUserStore()
const router = useRouter()
const isAdmin = computed(() => !!store.isAdmin)

const chartRef = ref(null)
let chart = null
let refreshTimer = null

const days = ref(1)
const summary = ref({ today_total: 0, today_good: 0, today_bad: 0, good_rate: 0 })
const trend = ref({ labels: [], total: [], good: [], rate: [] })
const byType = ref([])
const recent = ref([])
const latest = ref(null)
const lastFrameAt = ref(null)
const socketOnline = ref(false)
const streamUrl = ref('')
const imageError = ref(false)

// 摄像头直连（后端采集服务）
const camMode = ref('camera') // camera=后端直连摄像头，device=等设备端上传
const camStatus = ref({})
const camLoading = ref(false)
const switches = ref({ detect: true, snapshot: true, record: false })
let camTimer = null

// 录像文件列表（后端直接扫 uploads/videos，没有表）
const videos = ref([])
const videoDialog = ref(false)
const playing = ref(null)
let lastVideoCount = -1

const statCards = computed(() => [
  { key: 'total', label: '今日总数', value: summary.value.today_total, color: '#1f2937', foot: '今日累计上报' },
  { key: 'good', label: '合格', value: summary.value.today_good, color: '#22c55e', foot: 'result = good' },
  { key: 'bad', label: '不合格', value: summary.value.today_bad, color: '#ef4444', foot: 'result = bad' },
  { key: 'rate', label: '良品率', value: `${summary.value.good_rate}%`, color: '#1677ff', foot: '合格 / 总数' },
])

const lastFrameText = computed(() => {
  if (!lastFrameAt.value) return '—'
  const d = new Date(lastFrameAt.value)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

function shortTime(value) {
  if (!value) return '—'
  return String(value).slice(5, 16)
}

function reloadStream() {
  if (!store.token) return
  imageError.value = false
  // 两种画面源：
  //   /api/device/live   —— 后端自己抓的帧，全程在内存里，不落盘
  //   /api/device/stream —— 设备端（OpenMV / pc_camera_device.py）上传的 latest.jpg
  const path = camMode.value === 'camera' ? '/api/device/live' : '/api/device/stream'
  streamUrl.value = `${API_BASE}${path}?token=${encodeURIComponent(store.token)}&t=${Date.now()}`
}

function onModeChange() {
  streamUrl.value = ''
  imageError.value = false
  if (camMode.value === 'camera') pollCamera()
  else reloadStream()
}

// 采集状态：3 秒轮询一次。只有它有帧了才去接流，
// 否则会挂一个永远没画面的请求，看着像“卡住了”。
async function pollCamera() {
  try {
    const res = await deviceApi.cameraStatus()
    const s = res.data || {}
    camStatus.value = s
    switches.value = {
      detect: !!s.detect,
      snapshot: !!s.snapshot,
      record: !!s.record,
    }
    if (camMode.value === 'camera') {
      if (s.running && s.has_frame) {
        if (!streamUrl.value) reloadStream()
      } else {
        streamUrl.value = ''
      }
      // 录像段数变了就刷一次列表（默认 -1，首次也会刷）
      if (s.videos !== lastVideoCount) {
        lastVideoCount = s.videos ?? 0
        loadVideos()
      }
    }
  } catch (e) {
    // 状态查不到就保持上一次的值，等下一轮
  }
}

async function startCamera() {
  camLoading.value = true
  try {
    const res = await deviceApi.startCamera({
      fps: 8,
      detect: switches.value.detect,
      snapshot: switches.value.snapshot,
      record: switches.value.record,
    })
    camStatus.value = res.data || {}
    if (res.code === 0) {
      ElMessage.success('采集已启动')
      streamUrl.value = ''
      reloadStream()
    } else {
      ElMessage.error(res.msg || '启动失败')
    }
  } catch (e) {
    // 失败原因由拦截器提示
  } finally {
    camLoading.value = false
  }
}

async function stopCamera() {
  try {
    const res = await deviceApi.stopCamera()
    camStatus.value = res.data || {}
    streamUrl.value = ''
    ElMessage.success('采集已停止，摄像头已释放')
  } catch (e) {
    // 失败原因由拦截器提示
  }
}

// 三个开关互相独立：识别 / 命中存图 / 录像
async function patchSwitch(key, value) {
  try {
    const res = await deviceApi.cameraConfig({ [key]: value })
    camStatus.value = res.data || {}
    ElMessage.success(
      key === 'detect'
        ? `识别已${value ? '开启' : '关闭'}`
        : key === 'snapshot'
          ? `命中存图已${value ? '开启' : '关闭'}`
          : `录像已${value ? '开启' : '关闭'}`
    )
  } catch (e) {
    switches.value[key] = !value // 发不出去就回滚，别让界面撒谎
  }
}

// 录像文件：打开采集时才用得上，所以列表只在摄像头直连模式下显示
async function loadVideos() {
  try {
    const res = await deviceApi.videoList()
    const items = res.data?.items || []
    videos.value = items.map((v) => ({ ...v, fullUrl: `${API_BASE}${v.url}` }))
  } catch (e) {
    // 拦截器已提示，保持旧列表
  }
}

function playVideo(v) {
  playing.value = v
  videoDialog.value = true
}

async function removeVideo(v) {
  try {
    await ElMessageBox.confirm(
      `确认删除录像「${v.name}」？文件会从硬盘上直接删掉，不可恢复。`,
      '删除录像',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '再想想' }
    )
  } catch (e) {
    return // 点了取消
  }
  try {
    await deviceApi.deleteVideo(v.name)
    ElMessage.success('已删除')
    if (playing.value?.name === v.name) {
      videoDialog.value = false
      playing.value = null
    }
    await loadVideos()
  } catch (e) {
    // 原因由拦截器提示
  }
}

async function loadStats() {
  const res = await recordApi.stats(days.value)
  summary.value = res.data.summary
  trend.value = res.data.trend
  byType.value = res.data.by_type || []
  await nextTick()
  renderChart()
}

async function loadRecent() {
  const res = await recordApi.list({ page: 1, page_size: 8 })
  recent.value = res.data.items || []
  if (recent.value.length) latest.value = recent.value[0]
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)

  const t = trend.value
  chart.setOption(
    {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { top: 0, itemWidth: 12, itemHeight: 12 },
      grid: { left: 46, right: 46, top: 44, bottom: 28, containLabel: false },
      xAxis: {
        type: 'category',
        data: t.labels,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#dfe8f5' } },
        axisLabel: { color: '#6b7a90' },
      },
      yAxis: [
        {
          type: 'value',
          name: '数量',
          nameTextStyle: { color: '#6b7a90' },
          axisLabel: { color: '#6b7a90' },
          splitLine: { lineStyle: { color: '#eef3fa' } },
        },
        {
          type: 'value',
          name: '良品率 %',
          min: 0,
          max: 100,
          nameTextStyle: { color: '#6b7a90' },
          axisLabel: { color: '#6b7a90', formatter: '{value}%' },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '分拣数量',
          type: 'bar',
          data: t.total,
          barMaxWidth: 26,
          itemStyle: { color: '#1677ff', borderRadius: [4, 4, 0, 0] },
        },
        {
          name: '良品率',
          type: 'line',
          yAxisIndex: 1,
          data: t.rate,
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          itemStyle: { color: '#22c55e' },
          lineStyle: { width: 2, color: '#22c55e' },
        },
      ],
      animationDuration: 600,
    },
    true
  )
  chart.resize()
}

function bumpSummary(row) {
  const s = summary.value
  s.today_total += 1
  if (row.result === 'good') s.today_good += 1
  else s.today_bad += 1
  s.good_rate = s.today_total ? Number(((s.today_good / s.today_total) * 100).toFixed(1)) : 0
}

function scheduleStatsRefresh() {
  if (refreshTimer) return
  refreshTimer = setTimeout(async () => {
    refreshTimer = null
    try {
      await loadStats()
    } catch (e) {
      // 统计数据下次再校，不打断实时推送
    }
  }, 2000)
}

function bindSocket() {
  const socket = getSocket()

  socket.on('connect', () => {
    socketOnline.value = true
  })

  socket.on('disconnect', () => {
    socketOnline.value = false
  })

  socket.on('connect_error', () => {
    socketOnline.value = false
  })

  // 新分拣记录：直接插到列表头部并本地累加，再延时向服务端校正一次
  socket.on('new_record', (payload) => {
    if (!payload || !payload.id) return
    latest.value = payload
    recent.value = recent.value.filter((item) => item.id !== payload.id)
    recent.value.unshift(payload)
    if (recent.value.length > 8) recent.value.pop()
    bumpSummary(payload)
    scheduleStatsRefresh()
  })

  // 实时帧到达：更新“最近帧”时间；设备上报模式下第一次收到就启动画面
  socket.on('live_frame', (payload) => {
    lastFrameAt.value = payload?.ts || Date.now()
    if (camMode.value === 'device' && !streamUrl.value) reloadStream()
  })
}

function goRecord() {
  router.push('/record')
}

function onResize() {
  if (chart) chart.resize()
}

onMounted(async () => {
  bindSocket()
  window.addEventListener('resize', onResize)

  // 先问一次采集状态：没在跑就不再挂一个永远没画面的流
  await pollCamera()
  camTimer = setInterval(pollCamera, 3000)

  try {
    await Promise.all([loadStats(), loadRecent()])
  } catch (e) {
    // 请求失败已在拦截器提示，页面保持空态
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (camTimer) {
    clearInterval(camTimer)
    camTimer = null
  }
  if (refreshTimer) {
    clearTimeout(refreshTimer)
    refreshTimer = null
  }
  if (chart) {
    chart.dispose()
    chart = null
  }
  closeSocket()
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.panel {
  border-radius: 10px;
  border: 1px solid var(--app-border);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  font-weight: 600;
  font-size: 15px;
}

.panel-head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.top-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.video-panel {
  flex: 1 1 60%;
  min-width: 0;
}

.video-wrap {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
  background: #0b1526;
}

.video {
  display: block;
  width: 100%;
  height: 360px;
  object-fit: contain;
  background: #0b1526;
}

.video-placeholder {
  height: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #8fa6c4;
}

.ph-icon {
  font-size: 42px;
  color: #33506f;
}

.video-placeholder p {
  margin: 0;
  font-size: 14px;
  color: #c7d6ea;
}

.video-placeholder span {
  font-size: 12px;
  color: #7d94b2;
}

.video-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.04);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  color: #a9bcce;
  font-size: 12px;
}

.video-meta .ok {
  color: #4ade80;
}

.video-meta .bad {
  color: #f87171;
}

/* 采集控制条：与深色画面区同一套配色 */
.cam-bar {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f7f9fc;
  border: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cam-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.cam-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.cam-text {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.cam-err {
  color: #ef4444;
}

.cam-hint {
  color: #d97706;
  font-size: 12px;
}

/* 录像文件列表 */
.video-box {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--app-border);
}

.video-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.video-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.video-empty {
  color: #909399;
  margin: 6px 0 2px;
}

.video-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 5px 0;
  border-bottom: 1px dashed #f2f3f5;
}

.video-name {
  flex: 1;
  min-width: 0;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #606266;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.video-meta {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}

.video-player {
  width: 100%;
  max-height: 460px;
  background: #000;
  border-radius: 4px;
}

.video-dialog-tip {
  margin: 8px 0 0;
}

.cam-sep {
  width: 1px;
  height: 16px;
  background: var(--app-border);
  margin: 0 4px;
}

.stat-col {
  flex: 0 0 280px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 16px;
}

.stat-card {
  border-radius: 10px;
  border: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.stat-card :deep(.el-card__body) {
  padding: 18px;
}

.stat-label {
  font-size: 13px;
  color: var(--app-text-sub);
}

.stat-value {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.25;
  margin: 4px 0 2px;
}

.stat-foot {
  font-size: 12px;
  color: #98a5b8;
}

.bottom-row {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 320px;
}

.chart-panel {
  flex: 1 1 62%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chart {
  width: 100%;
  height: 300px;
}

.list-panel {
  flex: 1 1 38%;
  min-width: 260px;
}

.recent-list {
  max-height: 304px;
  overflow-y: auto;
}

.recent-item {
  padding: 8px 4px;
  border-bottom: 1px dashed #e9eff8;
}

.recent-item:last-child {
  border-bottom: none;
}

.recent-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.fruit {
  font-weight: 600;
  color: var(--app-text);
}

.recent-meta {
  display: flex;
  gap: 14px;
  margin-top: 3px;
  font-size: 12px;
  color: #98a5b8;
}

@media (max-width: 1200px) {
  .top-row {
    flex-direction: column;
  }

  .stat-col {
    flex: none;
    grid-template-columns: repeat(4, 1fr);
    grid-template-rows: none;
  }

  .bottom-row {
    flex-direction: column;
  }
}
</style>
