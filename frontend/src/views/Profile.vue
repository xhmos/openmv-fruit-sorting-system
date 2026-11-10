<template>
  <div class="profile-page">
    <el-row :gutter="16">
      <!-- 左：账号卡 -->
      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="account-card">
          <div class="avatar-wrap">
            <el-avatar :size="72" :src="avatarSrc" class="avatar">
              {{ initial }}
            </el-avatar>
            <div class="account-name">{{ info.username || '未登录' }}</div>
            <el-tag :type="store.isAdmin ? 'primary' : 'info'" effect="light" size="small">
              {{ store.roleText }}
            </el-tag>

            <div class="avatar-actions">
              <input
                ref="fileInput"
                class="avatar-input"
                type="file"
                accept="image/png,image/jpeg"
                @change="onPickAvatar"
              />
              <el-button size="small" :loading="uploading" @click="pickAvatar">
                {{ info.avatar ? '更换头像' : '上传头像' }}
              </el-button>
              <el-button
                v-if="info.avatar"
                size="small"
                text
                type="danger"
                @click="removeAvatar"
              >
                移除
              </el-button>
            </div>
            <div class="avatar-tip">jpg / png，2MB 以内</div>
          </div>

          <el-descriptions :column="1" border size="small" class="meta">
            <el-descriptions-item label="账号 ID">{{ info.id ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="账号状态">
              <el-tag v-if="info.is_active === false" type="danger" size="small">已禁用</el-tag>
              <el-tag v-else type="success" size="small">正常</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ info.create_time || '—' }}</el-descriptions-item>
            <el-descriptions-item label="后端地址">{{ apiBase }}</el-descriptions-item>
          </el-descriptions>

          <div class="account-actions">
            <el-button type="primary" plain :loading="refreshing" @click="refresh">
              刷新账号信息
            </el-button>
            <el-button @click="router.push('/dashboard')">回到实时监控</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右：使用说明 / 权限 / 关于 -->
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="panel-card">
          <el-tabs v-model="tab">
            <!-- 使用说明 -->
            <el-tab-pane label="使用说明" name="guide">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                title="下面按页面顺序说明每个模块怎么用"
                description="遇到操作不生效，先看最后一节「常见问题」，90% 的情况在那里有答案。"
                class="guide-alert"
              />

              <el-collapse v-model="activeBlocks">
                <el-collapse-item
                  v-for="block in guides"
                  :key="block.key"
                  :name="block.key"
                  :title="block.title"
                >
                  <ul class="guide-list">
                    <li v-for="(line, idx) in block.items" :key="idx">{{ line }}</li>
                  </ul>
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>

            <!-- 账号与权限 -->
            <el-tab-pane label="账号与权限" name="security">
              <el-table :data="roleRows" border size="small" class="role-table">
                <el-table-column prop="name" label="角色" width="110" />
                <el-table-column prop="who" label="本项目账号" width="150" />
                <el-table-column prop="can" label="可以做什么" />
                <el-table-column prop="cannot" label="不能做什么" />
              </el-table>

              <el-divider content-position="left">登录状态</el-divider>
              <ul class="guide-list">
                <li>登录凭证（JWT）有效期 <strong>8 小时</strong>，超过后接口会返回 401，需要重新登录。</li>
                <li>凭证保存在浏览器 localStorage，换浏览器或清缓存后需要重新登录。</li>
                <li>右上角点用户名可选「退出登录」，退出后本地凭证立即清除。</li>
                <li>账号被管理员禁用后，已登录的会话会在下次请求时被拒绝。</li>
                <li>公共电脑用完请务必退出登录，避免下一个人直接进入系统。</li>
              </ul>

              <el-divider content-position="left">遇到 401 / 403 怎么判断</el-divider>
              <ul class="guide-list">
                <li><strong>401</strong>：没登录、凭证过期或账号被禁用 —— 重新登录。</li>
                <li><strong>403</strong>：登录着但不是管理员，却在调管理员接口 —— 换 admin 账号。</li>
                <li><strong>429</strong>：请求太频繁（全局 200 次/分钟，登录更严）—— 等一分钟再试。</li>
              </ul>
            </el-tab-pane>

            <!-- 关于系统 -->
            <el-tab-pane label="关于系统" name="about">
              <el-descriptions :column="2" border size="small">
                <el-descriptions-item label="系统名称">果实智能分拣监控管理系统</el-descriptions-item>
                <el-descriptions-item label="版本">v1.0（2026-11）</el-descriptions-item>
                <el-descriptions-item label="后端">Python Flask + Flask-SQLAlchemy + Flask-SocketIO</el-descriptions-item>
                <el-descriptions-item label="前端">Vue3 + Element Plus + Axios + ECharts + Pinia</el-descriptions-item>
                <el-descriptions-item label="数据库">MySQL 8.0（库名 openmv_ai）</el-descriptions-item>
                <el-descriptions-item label="设备端">OpenMV + ESP32（MicroPython）</el-descriptions-item>
                <el-descriptions-item label="实时通信">Socket.IO 推送新记录 + 内存直传的摄像头画面（不落盘）</el-descriptions-item>
                <el-descriptions-item label="后端接口">6 个蓝图 / 37 个接口</el-descriptions-item>
              </el-descriptions>

              <el-divider content-position="left">没有板子怎么演示</el-divider>
              <p class="tip-text">
                板子不在手边时，用项目根目录的模拟脚本就能让看板动起来（画面 + 统计 + 实时推送一起生效）：
              </p>
              <pre class="cmd">cd C:\Users\10149\Desktop\openMV
.\backend\venv\Scripts\python.exe simulate_device.py --frames 9999 --interval 1 --report-every 3</pre>
              <p class="tip-text">
                <strong>--interval 不要低于 0.3 秒</strong>，否则会撞上 200 次/分钟的限流，表现为上报失败刷屏。
              </p>

              <el-divider content-position="left">数据与文件放在哪</el-divider>
              <ul class="guide-list">
                <li>分拣图片：<code>backend\uploads\records\</code>，按「90 天 / 2000 张」自动清理，删图时记录仍保留。</li>
                <li>录像文件：<code>backend\uploads\videos\</code>，看板上的「录像文件」列表能看到、播放、删除，删了就不可恢复。</li>
                <li>头像文件：<code>backend\uploads\avatars\</code>，换一次头像会自动删掉上一张。</li>
                <li>运行日志：<code>backend\logs\app.log</code>，按天轮转保留 14 天（用 VS Code 打开，别用 PowerShell 直接看中文）。</li>
                <li>系统配置：<code>backend\.env</code>，数据库密码、设备令牌、密钥都在这里。</li>
              </ul>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '../store/user'
import { authApi } from '../api'
import { API_BASE, uploadUrl } from '../config'

const router = useRouter()
const store = useUserStore()

const tab = ref('guide')
const refreshing = ref(false)
const info = reactive({
  id: null,
  username: '',
  role: '',
  is_active: true,
  create_time: '',
  avatar: '',
})

const apiBase = API_BASE
const initial = computed(() => (info.username || '?').slice(0, 1).toUpperCase())
// 后端返回的是 uploads 下的相对路径（如 avatars/xxx.jpg），拼成完整地址
const avatarSrc = computed(() => (info.avatar ? uploadUrl(info.avatar) : ''))
const fileInput = ref(null)
const uploading = ref(false)

// 默认展开第一节，其余折叠，避免一进来就是一屏文字
const activeBlocks = ref(['login'])

const guides = [
  {
    key: 'login',
    title: '一、登录与账号',
    items: [
      '管理员账号 admin / admin123；操作员账号 operator1 / op123456。',
      '注意区分：admin123 是系统登录密码，Aa123456.（末尾有点）是 MySQL 数据库密码，别混用。',
      '登录页已预填 admin，直接点「登录」即可；登录成功会跳回你原本想访问的页面。',
      '连续输错密码会触发限流，第 3 次左右提示「请求过于频繁」，等一分钟再试。',
      '头像在这个页面的左侧账号卡里传：点「上传头像」选 jpg / png（2MB 以内）；「更换头像」会自动删掉旧图，「移除」回到首字母占位。',
    ],
  },
  {
    key: 'dashboard',
    title: '二、实时监控（看板）',
    items: [
      '画面有两种来源，卡片右上角切换：「摄像头直连」（默认，后端自己开电脑摄像头）和「设备上报」（读 OpenMV 板 / pc_camera_device.py 推上来的帧）。',
      '摄像头直连要先点「启动采集」。抓到的帧只在内存里转给网页，不写磁盘，所以不会一天下来堆一堆图。',
      '三个开关互相独立：识别（跑不跑找果实的算法）、命中存图（识别到才存一张证据图并写一条记录）、录像（命中时另存一段短视频到 uploads/videos）。识别关着时另外两个不会触发。',
      '录像开关是单独取出来的一项：不想留视频文件就关掉，不影响存图，也不影响画面。',
      '控制条下面的「录像文件」列表：能看到文件名 / 大小 / 时间，点「播放」弹窗直接看，点「删除」把硬盘上的 mp4 删掉（不可恢复，只有管理员能删）。列表是直接扫 backend/uploads/videos 目录来的，不存数据库。',
      '右上：四张统计卡 —— 今日总数 / 合格 / 不合格 / 良品率，有新记录时实时往上跳。',
      '中下：ECharts 双 Y 轴图 —— 柱状是每日数量、折线是良品率，右上角可切换「近 1 天 / 近 7 天」。',
      '右下：最近分拣记录列表，新记录从顶部插入，最多保留 8 条。',
      '右上角显示「推送未连接」= Socket.IO 没连上（多半是凭证过期），重新登录一次即可。',
      '画面区域一直是灰的：摄像头直连模式下先点「启动采集」；设备上报模式下说明没有设备在上传帧。',
      '摄像头同一时间只能被一个程序打开。启动采集后 pc_camera_device.py 会打不开，想跑那个脚本先「停止采集」。',
      '统计数字会先跳一下、随后微调，这是「本地先加、2 秒后回查服务端校正」的防抖逻辑，不是算错。',
    ],
  },
  {
    key: 'record',
    title: '三、分拣记录',
    items: [
      '筛选：品种（下拉可搜索，也可直接手输如 mango）、结果（合格/不合格）、时间范围（默认起始 00:00:00、结束 23:59:59）。点「查询」生效，点「重置」清空条件。',
      '看大图：点缩略图会弹出原图预览；若提示图片已清理，说明该图已被自动清理策略回收。',
      '分页：底部可切 10 / 20 / 50 / 100 条一页，删完当前页最后一条会自动回退一页。',
      '批量删除：只有管理员能勾选（左侧多选框），删除会同时清掉磁盘上的图片文件。',
      '导出 Excel：只有管理员有按钮，导出的是当前筛选条件下的数据，不是全库。',
    ],
  },
  {
    key: 'setting',
    title: '四、参数配置',
    items: [
      '四组滑块对应 H/S/V 上下限，外加一个最小像素面积 min_area，范围与后端校验一致（H 0~179，S/V 0~255，面积 0~1000000）。',
      '每项都有 min ≤ max 校验，填反了会提示，保存不会写脏数据。',
      '重要：颜色阈值只有 min_area 会真正下发到板子。HSL 这一套是「对照留档」用的，OpenMV 的 find_blobs 认的是 LAB —— 换品种必须回板端用阈值编辑器重新取 LAB。',
      '保存后板子不是立刻生效，它每 10 秒拉一次参数，等十几秒再观察。',
      '操作员可以查看参数，但保存按钮只对管理员开放。',
    ],
  },
  {
    key: 'device',
    title: '五、设备连接',
    items: [
      '上半部分「我的设备」是保存过的设备，像电脑的 WiFi 列表：点「连接」复查状态，点「删除」只删记录、不动设备本身。',
      '新增设备：弹窗里选类型（摄像头 / 串口 / 网络流），从扫描清单里挑一个，填名字即可。保存的同时会立刻探测一次。',
      '连接未知设备：扫描表里没有的目标，用这个入口手动填端口号或流地址，可以先「测试连接」再保存。',
      '连接时会重新检查：摄像头看系统有没有识别到、状态是否正常；串口看端口在不在、驱动对不对；网络流会真发一次请求看能不能收到画面。',
      '打开「自动连接」只是给这个设备做个标记，方便你看出哪些是常用设备；它不会自动连接、也不会自动扫描，一切以你点按钮为准。',
      '下半部分是设备扫描：摄像头表里出现的，才是程序能直接抓帧的摄像头；标「内置」的是笔记本自带的那个。',
      '串口表给出 COM 端口和芯片型号。看到 CH340 / CP210x / FT232，基本就是单片机或机械臂控制板的调试口。',
      '扫描和连接都只核对设备列表，不会打开串口。打开串口可能让单片机复位（机械臂会突然动一下），所以没有做成自动占用。',
      '保存设备不等于占着设备。想看画面要么看板里「启动采集」让后端开摄像头，要么用 pc_camera_device.py 从设备端推帧，两者不能同时开。',
      '这一页只在你点「重新扫描」时才去枚举设备（约 4 秒），进页面不会自动扫，也不定时扫。',
      'OpenCV 只能按编号打开摄像头，认不了 Windows 设备名。填设备名也行，启动采集时会自动按 0~4 找第一个能出画面的；有多个摄像头建议直接填编号。',
      '新增 / 删除 / 连接只有管理员能操作，操作员只能查看。',
    ],
  },
  {
    key: 'user',
    title: '六、用户管理（仅管理员）',
    items: [
      '新增账号：用户名只能 3~20 位字母、数字或下划线，角色选 admin / operator。',
      '禁用账号：开关一关，该账号立刻无法登录，已登录的会话下次请求也会被拒。',
      '重置密码、改角色、删除账号都在列表右侧操作列里；开关失败会自动回滚，不会出现界面和库里不一致。',
      '操作员看不到这个菜单，直接改地址访问也会被路由守卫弹回看板，后端接口同样返回 403。',
    ],
  },
  {
    key: 'faq',
    title: '七、常见问题',
    items: [
      '页面打不开、浏览器说无法访问 → 前端没启动：cd frontend 后 npm run dev。',
      '页面能开但一片空白、接口全 401 → 后端没启动：检查 5000 端口是否在监听。',
      '手机或另一台电脑打不开 → 前端要用 npm run dev -- --host 启动，并确认与电脑在同一 WiFi。',
      '上传图片报「疑似改后缀绕过」→ 文件内容不是真 jpg/png，改用真图。',
      '后端启动报 Address already in use → 之前那个后端进程还在，先关掉再启动。',
      '突然所有接口都 401 → 密钥更换后旧凭证失效，退出重新登录。',
    ],
  },
]

const roleRows = [
  {
    name: '管理员',
    who: 'admin',
    can: '全部功能：看板、记录查询与删除、导出报表、修改识别参数、用户增删改',
    cannot: '—',
  },
  {
    name: '操作员',
    who: 'operator1',
    can: '看实时画面、看统计与历史记录、查看参数',
    cannot: '不能管理账号、不能删记录、不能改参数、不能导出报表',
  },
]

onMounted(async () => {
  Object.assign(info, store.userInfo || {})
  // 回库拉一次最新状态（比如刚被禁用、刚改过角色）
  try {
    const latest = await store.refreshMe()
    Object.assign(info, latest)
  } catch (e) {
    // 拉取失败不影响浏览说明，保持本地缓存展示
  }
})

async function refresh() {
  refreshing.value = true
  try {
    const latest = await store.refreshMe()
    Object.assign(info, latest)
    ElMessage.success('账号信息已刷新')
  } catch (e) {
    ElMessage.error('刷新失败，请重新登录后再试')
  } finally {
    refreshing.value = false
  }
}

// ---------------------------------------------------------------- 头像
function pickAvatar() {
  fileInput.value?.click()
}

async function onPickAvatar(e) {
  const file = e.target.files && e.target.files[0]
  e.target.value = '' // 清空，允许下次再选同一个文件
  if (!file) return

  // 前端先挡一遍，后端还会再校验文件头，改后缀骗不过去
  if (!/^image\/(jpeg|png)$/.test(file.type)) {
    ElMessage.warning('只支持 jpg / png 图片')
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 2MB，先压一下再传')
    return
  }

  const fd = new FormData()
  fd.append('file', file)
  uploading.value = true
  try {
    const res = await authApi.uploadAvatar(fd)
    Object.assign(info, res.data || {})
    // 同步一份到本地缓存，顶部导航和下次进页面都用新头像
    await store.refreshMe().catch(() => {})
    ElMessage.success('头像已更新')
  } catch (err) {
    // 失败原因由拦截器提示
  } finally {
    uploading.value = false
  }
}

async function removeAvatar() {
  try {
    await ElMessageBox.confirm('移除后回到「首字母」占位，确定吗？', '移除头像', {
      type: 'warning',
      confirmButtonText: '移除',
      cancelButtonText: '算了',
    })
  } catch (err) {
    return // 点了取消
  }
  try {
    const res = await authApi.resetAvatar()
    Object.assign(info, res.data || {})
    await store.refreshMe().catch(() => {})
    ElMessage.success('头像已移除')
  } catch (err) {
    // 失败原因由拦截器提示
  }
}
</script>

<style scoped>
.profile-page {
  max-width: 1280px;
}

.account-card {
  border-radius: 10px;
}

.avatar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 8px 0 18px;
  border-bottom: 1px solid var(--app-border);
  margin-bottom: 16px;
}

/* 头像：有图就显示图片，没图退回账号首字母 */
.avatar {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 30px;
  font-weight: 700;
  border: 2px solid var(--el-color-primary-light-7);
}

.avatar-input {
  display: none;
}

.avatar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.avatar-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.account-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--app-text);
}

.meta {
  margin-bottom: 16px;
}

.account-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}

.panel-card {
  border-radius: 10px;
  min-height: 520px;
}

.guide-alert {
  margin-bottom: 14px;
}

.guide-list {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
  color: var(--app-text);
  font-size: 13px;
}

.guide-list li {
  margin-bottom: 2px;
}

.tip-text {
  font-size: 13px;
  color: var(--app-text-sub);
  line-height: 1.8;
  margin: 8px 0;
}

.cmd {
  background: #f7f9fc;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12.5px;
  line-height: 1.7;
  color: #354052;
  overflow-x: auto;
  margin: 8px 0;
}

.role-table {
  margin-bottom: 4px;
}

code {
  background: #f4f6fa;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  color: #445;
}

:deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 600;
}
</style>
