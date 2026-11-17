<template>
  <div class="page">
    <el-alert
      v-if="!isAdmin"
      type="info"
      show-icon
      :closable="false"
      title="当前账号是操作员，只能查看参数，修改保存由管理员操作"
      class="tip"
    />
    <el-alert
      v-else
      type="success"
      show-icon
      :closable="false"
      title="参数保存后写入数据库，OpenMV 下次拉取 /api/setting/device 时生效，无需重启板子"
      class="tip"
    />
    <el-alert
      type="warning"
      show-icon
      :closable="false"
      title="注意：颜色阈值必须到 OpenMV 端用 LAB 取，本页 HSL 参数只作对照"
      description="OpenMV 的 find_blobs 只认 LAB 阈值，与本页 HSL 不是同一套色彩空间，不能直接换算。板子拉参时只有「最小面积 min_area」会真正生效，HSL 六项仅用于留档对照；要调整识别颜色范围，请在 OpenMV IDE 的阈值编辑器里取 LAB 值，写进 openmv_script/main.py 的 FRUITS。"
      class="tip"
    />

    <el-card shadow="never" class="card" v-loading="loading">
      <template #header>
        <div class="head">
          <span class="head-title">果实识别阈值</span>
          <span class="head-sub">HSL 颜色区间（仅对照留档）与最小面积（真正下发到板子）</span>
        </div>
      </template>

      <el-row :gutter="20">
        <el-col v-for="group in defs" :key="group.title" :xs="24" :md="12" :xl="12">
          <div class="group">
            <div class="group-title">{{ group.title }}</div>

            <div v-for="item in group.items" :key="item.key" class="row">
              <span class="row-label">{{ item.label }}</span>
              <el-slider
                v-model="form[item.key]"
                :min="0"
                :max="item.max"
                :step="item.step || 1"
                :disabled="!isAdmin"
                class="row-slider"
              />
              <el-input-number
                v-model="form[item.key]"
                :min="0"
                :max="item.max"
                :step="item.step || 1"
                :disabled="!isAdmin"
                controls-position="right"
                class="row-input"
              />
            </div>
          </div>
        </el-col>
      </el-row>

      <div class="foot">
        <span class="hint">键名：{{ keysText }}</span>
        <div class="foot-btns">
          <el-button @click="load">重新加载</el-button>
          <el-button v-if="isAdmin" @click="restoreDefault">恢复默认</el-button>
          <el-button v-if="isAdmin" type="primary" :loading="saving" @click="save">保存参数</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="card">
      <template #header><span class="head-title">设备端如何取参数</span></template>
      <div class="code-block">
        <div>GET http://&lt;服务器IP&gt;:5000/api/setting/device</div>
        <div>Header: X-Device-Token: &lt;.env 里的 DEVICE_TOKEN&gt;</div>
        <div>返回: {"code": 0, "data": {"h_min": 0, "h_max": 30, "s_min": 80, ...}}</div>
      </div>
      <p class="note">OpenMV 上电后拉一次即可；想跟网页实时同步，可以每 10 秒拉一次，用返回值重新设置阈值。</p>
    </el-card>

    <!-- ---------- 模型训练 ---------- -->
    <el-card shadow="never" class="card">
      <template #header>
        <div class="head">
          <span class="head-title">模型训练</span>
          <span class="head-sub">上传真实照片 → 划分数据集 → 训练 → 量化成 TFLite，整条链路都在这一页完成</span>
        </div>
      </template>

      <el-alert
        v-if="!trainEnvReady"
        type="error"
        show-icon
        :closable="false"
        title="本机找不到 train_env 或训练脚本，训练功能不可用"
        class="tip"
      />

      <!-- 数据集统计 -->
      <div class="ds-bar">
        <div v-for="c in dataset.classes" :key="c.name" class="ds-chip">
          <span class="ds-name">{{ c.name }}</span>
          <span class="ds-num" :class="{ low: c.count > 0 && c.count < 50 }">{{ c.count }}</span>
          <span class="ds-unit">张</span>
        </div>
        <div class="ds-chip total">
          <span class="ds-name">合计</span>
          <span class="ds-num">{{ dataset.total }}</span>
          <span class="ds-unit">张</span>
        </div>
      </div>
      <div class="ds-split">
        已划分：训练 {{ dataset.split.train }} / 验证 {{ dataset.split.val }} / 测试 {{ dataset.split.test }}
        <span class="ds-tip">目标尺寸 {{ dataset.target_size }}</span>
      </div>
      <div v-if="dataset.warnings.length" class="ds-warn">
        <span v-for="(w, i) in dataset.warnings" :key="i">· {{ w }}</span>
      </div>

      <!-- 第一步：上传 -->
      <div class="block">
        <div class="block-title">第一步 · 上传样本</div>
        <div class="ctl-row">
          <el-select
            v-model="uploadClass"
            placeholder="类别"
            :disabled="!isAdmin"
            style="width: 130px"
          >
            <el-option v-for="c in dataset.classes" :key="c.name" :label="c.name" :value="c.name" />
          </el-select>

          <el-upload
            v-model:file-list="fileList"
            :auto-upload="false"
            :limit="30"
            multiple
            accept=".jpg,.jpeg,.png"
          >
            <el-button :disabled="!isAdmin">选择图片</el-button>
          </el-upload>

          <el-button
            type="primary"
            :disabled="!isAdmin || !fileList.length || !uploadClass"
            :loading="uploading"
            @click="doUpload"
          >
            上传 {{ fileList.length }} 张
          </el-button>
        </div>
        <p class="note">
          保存时统一转成 320×240 的 JPEG，文件名自动编号，不会覆盖已有样本。单张限 2MB、一次最多 30 张。
          要新增类别，先改 <code>train/classes.txt</code> 再刷新本页。
        </p>
      </div>

      <!-- 第二步：划分 -->
      <div class="block">
        <div class="block-title">第二步 · 划分数据集（7 : 2 : 1）</div>
        <div class="ctl-row">
          <el-button :disabled="!isAdmin || taskRunning" :loading="splitting" @click="doSplit">
            划分数据集
          </el-button>
          <span class="ctl-hint">会先清空旧的 split 目录，按 seed=42 重新划分</span>
        </div>
      </div>

      <!-- 第三步：训练 -->
      <div class="block">
        <div class="block-title">第三步 · 训练</div>
        <div class="ctl-row">
          <span class="lbl">轮数</span>
          <el-input-number
            v-model="params.epochs"
            :min="1"
            :max="200"
            :disabled="!isAdmin || taskRunning"
            controls-position="right"
            style="width: 100px"
          />
          <span class="lbl">输入尺寸</span>
          <el-select v-model="params.img_size" :disabled="!isAdmin || taskRunning" style="width: 86px">
            <el-option v-for="s in sizeOptions" :key="s" :label="String(s)" :value="s" />
          </el-select>
          <span class="lbl">batch</span>
          <el-input-number
            v-model="params.batch"
            :min="1"
            :max="128"
            :disabled="!isAdmin || taskRunning"
            controls-position="right"
            style="width: 96px"
          />
          <span class="lbl">结构</span>
          <el-select v-model="params.arch" :disabled="!isAdmin || taskRunning" style="width: 150px">
            <el-option label="simple（轻量）" value="simple" />
            <el-option label="mobilenet" value="mobilenet" />
          </el-select>

          <el-button
            type="primary"
            :disabled="!isAdmin || taskRunning || !dataset.can_train"
            :loading="starting"
            @click="doStart"
          >
            开始训练
          </el-button>
          <el-button v-if="taskRunning" type="danger" plain @click="doCancel">取消</el-button>
        </div>
        <p class="note">
          训练在后台跑，会占满几核 CPU，期间网页其他操作可能变慢。30 轮通常需要几分钟，轮数越多越久。
        </p>
      </div>

      <!-- 进度与日志 -->
      <div v-if="showProgress" class="progress-box">
        <el-progress
          :percentage="status.progress || 0"
          :status="progressStatus"
          :stroke-width="14"
        />
        <div class="prog-line">
          <span>{{ stageText }}</span>
          <span v-if="status.epoch">第 {{ status.epoch }} / {{ status.total_epochs }} 轮</span>
        </div>
        <div v-if="status.tail && status.tail.length" class="log-box">
          <div v-for="(line, i) in status.tail" :key="i">{{ line }}</div>
        </div>
      </div>

      <!-- 训练结果 -->
      <div v-if="metrics" class="result">
        <div class="result-item">
          <span class="rl">测试集准确率</span>
          <span class="rv" :class="{ good: metrics.test_accuracy >= 0.9 }">
            {{ (metrics.test_accuracy * 100).toFixed(2) }}%
          </span>
        </div>
        <div class="result-item">
          <span class="rl">PC 单张推理</span>
          <span class="rv">{{ metrics.pc_latency_ms_per_image }} ms</span>
        </div>
        <div class="result-item">
          <span class="rl">训练用时</span>
          <span class="rv">{{ metrics.train_seconds }} 秒</span>
        </div>
        <div class="result-item">
          <span class="rl">类别</span>
          <span class="rv">{{ (metrics.class_names || []).join(' / ') }}</span>
        </div>
        <div class="result-item">
          <span class="rl">样本</span>
          <span class="rv">
            训练 {{ metrics.train_samples }} / 验证 {{ metrics.val_samples }} / 测试 {{ metrics.test_samples_total }}
          </span>
        </div>
      </div>

      <!-- 第四步：转换 -->
      <div class="block">
        <div class="block-title">第四步 · 量化成 TFLite（INT8）</div>
        <div class="ctl-row">
          <span class="lbl">校准张数</span>
          <el-input-number
            v-model="calibNum"
            :min="10"
            :max="300"
            :disabled="!isAdmin || taskRunning"
            controls-position="right"
            style="width: 100px"
          />
          <el-button
            :disabled="!isAdmin || taskRunning || !hasKeras"
            :loading="converting"
            @click="doConvert"
          >
            量化转换
          </el-button>
          <span class="ctl-hint">
            产物自动同步到 <code>openmv_script\</code>，直接拷到 SD 卡
          </span>
        </div>
        <div v-if="openmvModels.length" class="ctl-hint" style="margin-top: 8px">
          板端可用模型：{{ openmvModels.join(' / ') }}
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingApi, trainApi } from '../api'
import { useUserStore } from '../store/user'

const store = useUserStore()
const isAdmin = computed(() => store.isAdmin)

const loading = ref(false)
const saving = ref(false)

const defs = [
  {
    title: '色相 H（0 ~ 179）',
    items: [
      { key: 'h_min', label: '最小值', max: 179 },
      { key: 'h_max', label: '最大值', max: 179 },
    ],
  },
  {
    title: '饱和度 S（0 ~ 255）',
    items: [
      { key: 's_min', label: '最小值', max: 255 },
      { key: 's_max', label: '最大值', max: 255 },
    ],
  },
  {
    title: '亮度 V（0 ~ 255）',
    items: [
      { key: 'v_min', label: '最小值', max: 255 },
      { key: 'v_max', label: '最大值', max: 255 },
    ],
  },
  {
    title: '最小识别面积（像素）',
    items: [{ key: 'min_area', label: 'min_area', max: 1000000, step: 10 }],
  },
]

const form = reactive({
  h_min: 0,
  h_max: 30,
  s_min: 80,
  s_max: 255,
  v_min: 60,
  v_max: 255,
  min_area: 300,
})

const DEFAULT = { h_min: 0, h_max: 30, s_min: 80, s_max: 255, v_min: 60, v_max: 255, min_area: 300 }

const keysText = computed(() => Object.keys(form).join(' / '))

async function load() {
  loading.value = true
  try {
    const res = await settingApi.list()
    const items = res.data.items || []
    items.forEach((item) => {
      if (item.key in form && item.value !== null && item.value !== undefined) {
        form[item.key] = Number(item.value)
      }
    })
  } catch (e) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function restoreDefault() {
  Object.keys(DEFAULT).forEach((key) => {
    form[key] = DEFAULT[key]
  })
  ElMessage.info('已填入默认值，点「保存参数」才真正写入')
}

async function save() {
  const pairs = [
    ['h_min', 'h_max'],
    ['s_min', 's_max'],
    ['v_min', 'v_max'],
  ]
  for (const [low, high] of pairs) {
    if (form[low] > form[high]) {
      ElMessage.error(`${low} 不能大于 ${high}（当前 ${form[low]} > ${form[high]}）`)
      return
    }
  }

  try {
    await ElMessageBox.confirm(
      '修改识别阈值会影响 OpenMV 的识别结果，确认保存？',
      '保存确认',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }

  saving.value = true
  try {
    const res = await settingApi.update({ ...form })
    ElMessage.success(res.msg || '已保存')
    await load()
  } catch (e) {
    // 拦截器已提示（范围越界、min>max 等后端也会拦）
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- 模型训练
const dataset = reactive({
  classes: [],
  extra_classes: [],
  total: 0,
  split: { train: 0, val: 0, test: 0 },
  can_train: false,
  train_env_ready: false,
  warnings: [],
  target_size: '320×240',
})

const status = reactive({
  running: false,
  stage: 'idle',
  progress: 0,
  epoch: null,
  total_epochs: null,
  tail: [],
  exit_code: null,
  metrics: null,
  message: '',
})

const params = reactive({ epochs: 30, img_size: 96, batch: 32, arch: 'simple' })
const sizeOptions = [32, 48, 64, 96, 128, 160]

const fileList = ref([])
const uploadClass = ref('')
const uploading = ref(false)
const splitting = ref(false)
const starting = ref(false)
const converting = ref(false)
const calibNum = ref(100)
const openmvModels = ref([])
const diskMetrics = ref(null)
const hasKerasFile = ref(false)

const taskRunning = computed(() => !!status.running)
const trainEnvReady = computed(() => !!dataset.train_env_ready)
const hasKeras = computed(() => hasKerasFile.value)
const metrics = computed(() => status.metrics || diskMetrics.value)
const showProgress = computed(() => !!status.running || status.stage !== 'idle')

const progressStatus = computed(() => {
  if (status.running) return ''
  return status.exit_code === 0 ? 'success' : 'exception'
})

const stageText = computed(() => {
  if (status.running) {
    if (status.stage === 'converting') return '正在量化转换…'
    if (status.epoch) return `训练中第 ${status.epoch} / ${status.total_epochs} 轮`
    return '正在准备数据…'
  }
  if (status.stage === 'training_done') {
    return status.exit_code === 0 ? '训练完成' : '训练失败，请看下面的日志'
  }
  if (status.stage === 'converting_done') {
    return status.exit_code === 0 ? '转换完成' : '转换失败，请看下面的日志'
  }
  if (status.stage === 'cancelled') return '已取消'
  return '空闲'
})

async function loadDataset() {
  try {
    const res = await trainApi.dataset()
    Object.assign(dataset, res.data || {})
    if (!uploadClass.value && dataset.classes.length) {
      uploadClass.value = dataset.classes[0].name
    }
  } catch (e) {
    // 拦截器已提示
  }
}

async function loadModels() {
  try {
    const res = await trainApi.models()
    const d = res.data || {}
    diskMetrics.value = d.metrics || null
    openmvModels.value = d.openmv_models || []
    hasKerasFile.value = (d.items || []).some((m) => m.name.endsWith('.keras'))
  } catch (e) {
    // 拦截器已提示
  }
}

async function refreshStatus() {
  try {
    const res = await trainApi.status()
    Object.assign(status, res.data || {})
    // 任务刚结束的那一次，顺手把模型清单和统计刷新
    if (!status.running && status.stage !== 'idle') {
      loadModels()
      loadDataset()
    }
  } catch (e) {
    // 拦截器已提示
  }
}

let pollTimer = null

function startPoll() {
  stopPoll()
  pollTimer = setInterval(refreshStatus, 3000)
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function doUpload() {
  if (!uploadClass.value) {
    ElMessage.warning('请先选择类别')
    return
  }
  const files = fileList.value.map((f) => f.raw).filter(Boolean)
  if (!files.length) {
    ElMessage.warning('没有可上传的文件')
    return
  }

  const fd = new FormData()
  fd.append('class_name', uploadClass.value)
  files.forEach((f) => fd.append('file', f))

  uploading.value = true
  try {
    const res = await trainApi.upload(fd)
    const d = res.data || {}
    if (d.dataset) Object.assign(dataset, d.dataset)

    if (d.failed && d.failed.length) {
      const detail = d.failed.map((x) => `${x.name}（${x.reason}）`).join('；')
      ElMessage.warning(`${res.msg}，${d.failed.length} 张没存进去：${detail}`)
    } else {
      ElMessage.success(res.msg || '上传完成')
    }
    fileList.value = []
  } catch (e) {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

async function doSplit() {
  splitting.value = true
  try {
    const res = await trainApi.split()
    if (res.data && res.data.dataset) Object.assign(dataset, res.data.dataset)
    ElMessage.success('划分完成')
  } catch (e) {
    // 拦截器已提示（后端把失败日志放在 data.log）
  } finally {
    splitting.value = false
  }
}

async function doStart() {
  try {
    await ElMessageBox.confirm(
      `开始训练 ${params.epochs} 轮？训练期间会占满几核 CPU，完成前不建议再操作本机。`,
      '训练确认',
      { type: 'warning', confirmButtonText: '开始训练', cancelButtonText: '取消' }
    )
  } catch (e) {
    return
  }

  starting.value = true
  try {
    const res = await trainApi.start({ ...params })
    ElMessage.success(res.msg || '训练已启动')
    await refreshStatus()
  } catch (e) {
    // 拦截器已提示
  } finally {
    starting.value = false
  }
}

async function doCancel() {
  try {
    await ElMessageBox.confirm(
      '确定取消当前任务？已经训练完的轮次不会保留。',
      '取消确认',
      { type: 'warning', confirmButtonText: '取消任务', cancelButtonText: '再等等' }
    )
  } catch (e) {
    return
  }

  try {
    await trainApi.cancel()
    ElMessage.success('已取消')
    await refreshStatus()
  } catch (e) {
    // 拦截器已提示
  }
}

async function doConvert() {
  converting.value = true
  try {
    const res = await trainApi.convert(calibNum.value)
    ElMessage.success(res.msg || '转换已启动')
    await refreshStatus()
  } catch (e) {
    // 拦截器已提示
  } finally {
    converting.value = false
  }
}

onMounted(() => {
  load()
  loadDataset()
  loadModels()
  refreshStatus()
  startPoll()
})

onBeforeUnmount(stopPoll)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tip {
  border-radius: 8px;
}

.card {
  border-radius: 10px;
  border: 1px solid var(--app-border);
}

.head {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.head-title {
  font-weight: 600;
  font-size: 15px;
}

.head-sub {
  font-size: 12px;
  color: var(--app-text-sub);
}

.group {
  padding: 4px 4px 12px;
}

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: #33445c;
  margin-bottom: 6px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
  line-height: 16px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
}

.row-label {
  width: 62px;
  flex: none;
  font-size: 13px;
  color: var(--app-text-sub);
}

.row-slider {
  flex: 1;
  min-width: 120px;
}

.row-input {
  width: 120px;
  flex: none;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--app-border);
}

.hint {
  font-size: 12px;
  color: #98a5b8;
}

.foot-btns {
  display: flex;
  gap: 8px;
}

.code-block {
  background: #0b1526;
  color: #c7d6ea;
  border-radius: 8px;
  padding: 12px 14px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.9;
  overflow-x: auto;
}

.note {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--app-text-sub);
}

/* ---------------- 模型训练区块 ---------------- */
.ds-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.ds-chip {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  background: #f4f7fb;
  border: 1px solid var(--app-border);
}

.ds-chip.total {
  background: #eef4ff;
  border-color: #cfe0ff;
}

.ds-name {
  font-size: 13px;
  color: #33445c;
  font-weight: 600;
}

.ds-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--el-color-primary);
  line-height: 1;
}

.ds-num.low {
  color: #e6a23c;
}

.ds-unit {
  font-size: 12px;
  color: #98a5b8;
}

.ds-split {
  font-size: 12px;
  color: var(--app-text-sub);
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 2px 2px 10px;
}

.ds-tip {
  color: #a8b4c6;
}

.ds-warn {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  color: #e6a23c;
  padding: 0 2px 10px;
}

.block {
  padding: 14px 2px;
  border-top: 1px dashed var(--app-border);
}

.block-title {
  font-size: 13px;
  font-weight: 600;
  color: #33445c;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
  line-height: 16px;
}

.ctl-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.lbl {
  font-size: 12px;
  color: var(--app-text-sub);
}

.ctl-hint {
  font-size: 12px;
  color: #98a5b8;
}

.progress-box {
  padding: 12px 2px;
  border-top: 1px dashed var(--app-border);
}

.prog-line {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--app-text-sub);
  margin-top: 6px;
}

.log-box {
  margin-top: 10px;
  max-height: 200px;
  overflow-y: auto;
  background: #0b1526;
  color: #c7d6ea;
  border-radius: 8px;
  padding: 10px 12px;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
}

.result {
  display: flex;
  flex-wrap: wrap;
  gap: 18px 28px;
  padding: 12px 2px;
  border-top: 1px dashed var(--app-border);
}

.result-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.rl {
  font-size: 12px;
  color: var(--app-text-sub);
}

.rv {
  font-size: 14px;
  font-weight: 600;
  color: #33445c;
}

.rv.good {
  color: #12b76a;
}

.note code,
.ctl-hint code {
  background: #f2f5f9;
  padding: 1px 5px;
  border-radius: 4px;
  font-family: Consolas, 'Courier New', monospace;
  color: #4a5b70;
}

/* ---------- 手机适配（≤768px） ---------- */
@media (max-width: 768px) {
  .block {
    padding: 12px 0;
  }

  /* 参数行：标签和输入框各占一行，避免固定宽度的输入框把标签挤掉 */
  .ctl-row {
    gap: 8px;
  }

  .ctl-row .lbl {
    flex: 0 0 auto;
  }

  /* 保存 / 恢复默认：两个按钮平分一行，手指好点 */
  .foot-btns .el-button {
    flex: 1 1 0;
    margin-left: 0 !important;
  }

  .log-box {
    max-height: 160px;
    font-size: 11px;
    padding: 8px 10px;
  }

  .result {
    gap: 10px 18px;
  }

  .rv {
    font-size: 13px;
  }

  .prog-line {
    flex-wrap: wrap;
    gap: 4px;
  }

  .ds-chip {
    font-size: 11px;
  }
}
</style>
