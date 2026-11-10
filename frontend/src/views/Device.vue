<template>
  <div class="page">
    <el-alert
      type="info"
      show-icon
      :closable="false"
      class="top-tip"
      title="保存过的设备会一直留在「我的设备」里，随时点「连接」复查，也可以删除"
      description="扫描只读取 Windows 的设备列表，不打开串口、不发送任何指令，因此不会让机械臂动作。真正开始采集图像时，由 pc_camera_device.py 这类脚本去占用设备，后端不长期占着摄像头。"
    />

    <!-- 我的设备：类似电脑 WiFi 的已保存网络 -->
    <el-card shadow="never" class="card" v-loading="savedLoading">
      <template #header>
        <div class="head">
          <div class="head-left">
            <span class="head-title">我的设备</span>
            <span class="head-sub">
              {{ saved.length ? `已保存 ${saved.length} 个` : '还没有保存过设备' }}
            </span>
          </div>
          <div class="head-right">
            <el-button
              size="small"
              :loading="connectingAll"
              :disabled="!isAdmin || !saved.length"
              @click="connectAll"
            >
              全部连接
            </el-button>
            <el-button size="small" type="primary" :disabled="!isAdmin" @click="openDialog('scan')">
              新增设备
            </el-button>
            <el-button size="small" :disabled="!isAdmin" @click="openDialog('manual')">
              连接未知设备
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="saved" border stripe empty-text="点右上角「新增设备」把常用的设备存进来">
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.dev_type)" effect="plain">
              {{ typeText(row.dev_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连接目标" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono">{{ row.target }}</span>
          </template>
        </el-table-column>
        <el-table-column label="自动连接" width="100" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.auto_connect"
              size="small"
              :disabled="!isAdmin"
              @change="onToggleAuto(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="130" align="center">
          <template #default="{ row }">
            <el-tooltip :content="row.last_message || '还没有连接过'" placement="top">
              <el-tag size="small" :type="savedStatusType(row.last_status)">
                {{ savedStatusText(row.last_status) }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="最近连接" width="160" align="center">
          <template #default="{ row }">
            <span class="muted">{{ row.last_connect_time || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :disabled="!isAdmin" @click="connectOne(row)">
              连接
            </el-button>
            <el-button link type="danger" size="small" :disabled="!isAdmin" @click="removeSaved(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!isAdmin" class="role-tip">当前账号是操作员，只能查看设备列表，新增/删除/连接需要管理员。</div>
    </el-card>

    <!-- 本机设备识别（原有扫描） -->
    <el-card
      shadow="never"
      class="card"
      v-loading="loading"
      element-loading-text="正在枚举设备，首次通常需要几秒"
    >
      <template #header>
        <div class="head">
          <div class="head-left">
            <span class="head-title">本机设备识别</span>
            <span class="head-sub">{{ summaryText }}</span>
          </div>
          <div class="head-right">
            <span class="head-tip">只在你点「重新扫描」时才去枚举，不会自己定时扫</span>
            <el-button type="primary" :loading="loading" @click="scan(true)">重新扫描</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="16" class="stats">
        <el-col :xs="12" :sm="6">
          <div class="stat">
            <div class="stat-num">{{ cameras.length }}</div>
            <div class="stat-label">摄像头设备</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat">
            <div class="stat-num">{{ ports.length }}</div>
            <div class="stat-label">串口设备</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat">
            <div class="stat-num">{{ boardPorts.length }}</div>
            <div class="stat-label">疑似开发板</div>
          </div>
        </el-col>
        <el-col :xs="12" :sm="6">
          <div class="stat">
            <div class="stat-num small">{{ host.name || '-' }}</div>
            <div class="stat-label">当前主机</div>
          </div>
        </el-col>
      </el-row>

      <div class="block-title">摄像头</div>
      <el-table :data="cameras" border stripe empty-text="没有识别到摄像头">
        <el-table-column prop="name" label="设备名" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.builtin_guess ? 'info' : 'success'" effect="plain">
              {{ row.builtin_guess ? '内置' : '外接' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="instance" label="实例 ID" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :disabled="!isAdmin" @click="quickAdd('camera', row.name)">
              保存
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="block-title">串口</div>
      <el-table :data="ports" border stripe empty-text="没有识别到串口设备">
        <el-table-column prop="port" label="端口" width="90" align="center">
          <template #default="{ row }">
            <span class="mono">{{ row.port || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="设备名" min-width="220" show-overflow-tooltip />
        <el-table-column label="芯片" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.chip" size="small" type="warning" effect="plain">{{ row.chip }}</el-tag>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="hint" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              size="small"
              :disabled="!isAdmin || !row.port"
              @click="quickAdd('serial', row.port)"
            >
              保存
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="tips">
        <div v-for="(t, i) in tips" :key="i" class="tip-line">
          <span class="dot"></span>{{ t }}
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card">
      <template #header>
        <span class="head-title">接入指引</span>
      </template>
      <el-collapse v-model="openedPanels">
        <el-collapse-item title="1. 接摄像头（USB 摄像头 / OpenMV 板）" name="1">
          <p class="guide-line">拿一根 <b>USB 数据线</b>（只能充电的线不行）把摄像头接到电脑。</p>
          <p class="guide-line">插上后回到本页点「重新扫描」：</p>
          <p class="guide-line">· 出现在「摄像头」表里 → 系统已识别为摄像头，直接可用；</p>
          <p class="guide-line">· 只出现在「串口」表里 → 是 OpenMV / 开发板那类主控板，需要走「板子抓图 → 串口传电脑」的方式。</p>
        </el-collapse-item>
        <el-collapse-item title="2. 接机械臂控制板" name="2">
          <p class="guide-line">机械臂控制板通常走 USB 转串口，会以 CH340 / CP210x / FT232 这类名字出现在「串口」表。</p>
          <p class="guide-line">看到它就说明板子已经和电脑通上了；至于能不能发指令控制动作，还要看板子的固件协议。</p>
          <p class="guide-line">注意：本页连接时只核对端口存在、驱动正常，<b>不会去打开串口</b>。真正发指令时程序一打开串口可能让单片机复位，所以第一次测试要先把机械臂架空、动作角度给小。</p>
        </el-collapse-item>
        <el-collapse-item title="3. 为什么插上了还是看不到" name="3">
          <p class="guide-line">按顺序排查：数据线是不是只能充电 → 设备有没有上电（指示灯亮不亮）→ 换一个 USB 口 → 换一台电脑试。</p>
          <p class="guide-line">设备管理器里如果出现带黄色感叹号的未知设备，是驱动没装，需要装对应芯片的驱动。</p>
        </el-collapse-item>
        <el-collapse-item title="4. 「我的设备」里的连接是什么意思" name="4">
          <p class="guide-line">保存的只是「怎么连」的参数和最近一次结果，不是占着设备不放。所以可以放心保存多个设备。</p>
          <p class="guide-line">点「连接」会重新检查一次：摄像头看系统有没有识别到、状态是否正常；串口看端口在不在、驱动对不对；网络流会真发一次请求看能不能收到画面。</p>
          <p class="guide-line">连上之后开始采集图像，仍然用项目里的 <b>pc_camera_device.py</b>：摄像头填序号、网络流直接填地址。</p>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <!-- 新增设备 / 连接未知设备 小窗 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px" @closed="resetDialog">
      <el-form label-width="88px">
        <el-form-item label="设备类型">
          <el-select v-model="form.dev_type" style="width: 100%" @change="onTypeChange">
            <el-option label="摄像头（本机 UVC）" value="camera" />
            <el-option label="串口设备（控制板 / 开发板）" value="serial" />
            <el-option label="网络流（手机当相机）" value="stream" />
          </el-select>
        </el-form-item>

        <el-form-item :label="targetLabel">
          <el-select
            v-if="form.dev_type !== 'stream' && scanOptions.length"
            v-model="form.target"
            filterable
            allow-create
            default-first-option
            style="width: 100%"
            :placeholder="targetPlaceholder"
          >
            <el-option
              v-for="opt in scanOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <el-input
            v-else
            v-model="form.target"
            :placeholder="targetPlaceholder"
            clearable
          />
          <div class="field-hint">{{ targetHint }}</div>
        </el-form-item>

        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="30" :placeholder="form.target || '留空就用连接目标当名称'" />
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="form.note" maxlength="60" placeholder="例如：机械臂控制板、桌上的外接摄像头" />
        </el-form-item>

        <el-form-item label="自动连接">
          <el-switch v-model="form.auto_connect" />
          <span class="field-hint inline">打开后进入本页会自动复查一次状态</span>
        </el-form-item>

        <el-form-item v-if="form.dev_type === 'stream'" label=" ">
          <span class="field-hint">手机装 IP Webcam / DroidCam，把显示出来的 http://IP:8080/video 地址填到上面即可。</span>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="testResult"
        :type="testResult.ok ? 'success' : 'error'"
        :closable="false"
        show-icon
        class="probe-result"
        :title="testResult.ok ? '能连上' : '连不上'"
        :description="testResult.message"
      />

      <template #footer>
        <el-button :loading="testing" @click="testConnection">测试连接</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDevice">保存并连接</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { systemApi } from '../api'
import { useUserStore } from '../store/user'

defineOptions({ name: 'DeviceConnect' })

const store = useUserStore()
const isAdmin = computed(() => !!store.isAdmin)

// ---------- 已保存设备 ----------
const saved = ref([])
const savedLoading = ref(false)
const connectingAll = ref(false)

// ---------- 扫描结果 ----------
const loading = ref(false)
const cameras = ref([])
const ports = ref([])
const tips = ref([])
const host = ref({})
const scannedAt = ref({ time: '', cached: false })
const openedPanels = ref(['1'])

// ---------- 弹窗 ----------
const dialogVisible = ref(false)
const dialogMode = ref('scan') // scan=从扫描结果选，manual=连接未知设备
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)
const form = ref({
  dev_type: 'camera',
  target: '',
  name: '',
  note: '',
  auto_connect: true,
})

const dialogTitle = computed(() =>
  dialogMode.value === 'manual' ? '连接未知设备' : '新增设备'
)

const TYPE_TEXT = { camera: '摄像头', serial: '串口', stream: '网络流' }
const TYPE_TAG = { camera: 'primary', serial: 'warning', stream: 'success' }

function typeText(t) {
  return TYPE_TEXT[t] || t
}
function typeTag(t) {
  return TYPE_TAG[t] || 'info'
}

const targetLabel = computed(() =>
  form.value.dev_type === 'camera' ? '摄像头' : form.value.dev_type === 'serial' ? '端口' : '流地址'
)

const targetPlaceholder = computed(() => {
  if (form.value.dev_type === 'camera') return '选系统识别到的摄像头，或直接填序号 0 / 1'
  if (form.value.dev_type === 'serial') return '选 COM 口，例如 COM7'
  return 'http://192.168.1.5:8080/video'
})

const targetHint = computed(() => {
  if (form.value.dev_type === 'camera')
    return '选设备名最准；填数字是给采集脚本当 --index 用，序号从 0 开始。'
  if (form.value.dev_type === 'serial')
    return '填端口号即可。这里只核对端口在不在，不会打开串口，所以不会让板子复位。'
  return '填手机 IP Webcam 这类 MJPEG 地址；保存后点「测试连接」会真发一次请求。'
})

// 扫描到的候选，跟着设备类型变
const scanOptions = computed(() => {
  if (form.value.dev_type === 'camera') {
    return cameras.value.map((c) => ({
      value: c.name,
      label: `${c.name}${c.builtin_guess ? '（内置）' : ''}`,
    }))
  }
  if (form.value.dev_type === 'serial') {
    return ports.value
      .filter((p) => p.port)
      .map((p) => ({
        value: p.port,
        label: `${p.port} — ${p.name}${p.chip ? ' [' + p.chip + ']' : ''}`,
      }))
  }
  return []
})

const boardPorts = computed(() => ports.value.filter((p) => p.chip && !p.chip.includes('蓝牙')))

const summaryText = computed(() => {
  if (!scannedAt.value.time) return '尚未扫描'
  const cached = scannedAt.value.cached ? '（缓存结果）' : ''
  return `扫描时间 ${scannedAt.value.time}${cached}`
})

function statusType(status) {
  const s = (status || '').toUpperCase()
  if (s === 'OK') return 'success'
  if (s === 'ERROR' || s === 'UNKNOWN') return 'info'
  return 'warning'
}

function savedStatusType(s) {
  if (s === 'ok') return 'success'
  if (s === 'fail') return 'danger'
  return 'info'
}

function savedStatusText(s) {
  if (s === 'ok') return '正常'
  if (s === 'fail') return '连不上'
  return '未连接'
}

// ---------- 扫描 ----------
async function scan(force = false) {
  loading.value = true
  try {
    const res = await systemApi.devices(force)
    const data = res.data || {}
    cameras.value = data.cameras || []
    ports.value = data.ports || []
    tips.value = data.tips || []
    host.value = data.host || {}
    scannedAt.value = { time: data.scanned_at || '', cached: !!data.cached }
    if (!data.ok && data.error) {
      tips.value = [data.error].concat(tips.value)
    }
  } catch (e) {
    tips.value = ['扫描请求失败：' + (e?.message || '未知错误')]
  } finally {
    loading.value = false
  }
}

// ---------- 已保存设备 ----------
async function loadSaved() {
  savedLoading.value = true
  try {
    const res = await systemApi.savedList()
    saved.value = (res.data?.items || []).slice()
  } catch (e) {
    // 具体原因由 axios 拦截器统一提示，这里只保证页面不崩
  } finally {
    savedLoading.value = false
  }
}

async function connectOne(row, silent = false) {
  try {
    const res = await systemApi.connectDevice(row.id)
    const item = res.data?.item
    if (item) {
      const idx = saved.value.findIndex((d) => d.id === item.id)
      if (idx >= 0) saved.value[idx] = item
    }
    if (!silent) {
      const p = res.data?.probe || {}
      if (p.ok) ElMessage.success(`「${item?.name || row.name}」连接成功`)
      else ElMessage.error(`「${item?.name || row.name}」连不上：${p.message || ''}`)
    }
  } catch (e) {
    // 失败原因由拦截器提示
  }
}

async function connectAll() {
  connectingAll.value = true
  let ok = 0
  let fail = 0
  try {
    for (const row of saved.value.slice()) {
      try {
        const res = await systemApi.connectDevice(row.id)
        const item = res.data?.item
        if (item) {
          const idx = saved.value.findIndex((d) => d.id === item.id)
          if (idx >= 0) saved.value[idx] = item
        }
        if (res.data?.probe?.ok) ok += 1
        else fail += 1
      } catch (e) {
        fail += 1
      }
    }
    if (fail === 0) ElMessage.success(`全部连接成功（${ok} 个）`)
    else ElMessage.warning(`连接完成：成功 ${ok} 个，失败 ${fail} 个`)
  } finally {
    connectingAll.value = false
  }
}

async function onToggleAuto(row) {
  try {
    await systemApi.toggleAuto(row.id, row.auto_connect)
  } catch (e) {
    row.auto_connect = !row.auto_connect
    // 失败原因由拦截器提示，这里负责把开关弹回原值
  }
}

async function removeSaved(row) {
  try {
    await ElMessageBox.confirm(
      `确定从列表里删除「${row.name}」吗？只删这条记录，不会动系统里的设备和驱动。`,
      '删除设备',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }
  try {
    await systemApi.removeDevice(row.id)
    saved.value = saved.value.filter((d) => d.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) {
    // 失败原因由拦截器提示
  }
}

// ---------- 弹窗 ----------
function resetDialog() {
  testResult.value = null
  form.value = { dev_type: 'camera', target: '', name: '', note: '', auto_connect: true }
}

function openDialog(mode) {
  resetDialog()
  dialogMode.value = mode
  dialogVisible.value = true
}

function onTypeChange() {
  form.value.target = ''
  testResult.value = null
  // 切类型时顺手带上第一个候选，省得用户空着
  if (dialogMode.value === 'scan' && scanOptions.value.length) {
    form.value.target = scanOptions.value[0].value
  }
}

// 从扫描表里一键保存
function quickAdd(devType, target) {
  resetDialog()
  dialogMode.value = 'scan'
  form.value.dev_type = devType
  form.value.target = target || ''
  dialogVisible.value = true
}

async function testConnection() {
  if (!form.value.target) {
    ElMessage.warning('先选或填要连接的目标')
    return
  }
  testing.value = true
  try {
    const res = await systemApi.probe(form.value.dev_type, form.value.target)
    testResult.value = res.data || { ok: false, message: '返回内容为空' }
  } catch (e) {
    testResult.value = { ok: false, message: '测试请求失败' }
  } finally {
    testing.value = false
  }
}

async function saveDevice() {
  if (!form.value.target) {
    ElMessage.warning('先选或填要连接的目标')
    return
  }
  saving.value = true
  try {
    const res = await systemApi.saveDevice({
      dev_type: form.value.dev_type,
      target: form.value.target,
      name: form.value.name,
      note: form.value.note,
      auto_connect: form.value.auto_connect,
    })
    const probe = res.data?.probe || {}
    if (probe.ok) ElMessage.success('已保存并连接成功')
    else ElMessage.warning(`已保存，但暂时连不上：${probe.message || ''}`)
    dialogVisible.value = false
    await loadSaved()
  } catch (e) {
    // 失败原因（例如「这个设备已经在列表里了」）由拦截器提示
  } finally {
    saving.value = false
  }
}

// ---------- 进页面 ----------
// 只加载「我的设备」列表（这是读库，不触发任何设备扫描），
// 扫描、连接全部交给用户点按钮，避免一进页面就起 PowerShell 枚举、还要等好几秒。
onMounted(async () => {
  await loadSaved()
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
}

.top-tip {
  border-radius: 10px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.head-title {
  font-weight: 600;
  font-size: 15px;
}

.head-sub {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.stats {
  margin-bottom: 18px;
}

.stat {
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
  padding: 14px 16px;
}

.stat-num {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}

.stat-num.small {
  font-size: 15px;
  font-weight: 600;
  word-break: break-all;
}

.stat-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  margin: 8px 0 10px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
}

.tips {
  margin-top: 16px;
  padding: 12px 14px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.tip-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--el-color-primary);
  margin-top: 8px;
  flex: 0 0 5px;
}

.mono {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}

.muted {
  color: var(--el-text-color-placeholder);
  font-size: 12.5px;
}

.guide-line {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}

.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin-top: 2px;
}

.field-hint.inline {
  margin-top: 0;
  margin-left: 10px;
}

.probe-result {
  border-radius: 8px;
}

.role-tip {
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
}
</style>
