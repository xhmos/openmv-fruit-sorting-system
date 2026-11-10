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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingApi } from '../api'
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

onMounted(load)
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
</style>
