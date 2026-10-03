<script setup lang="ts">
/**
 * 监控看板（M7）：全局总览统计 + 节点瓶颈分析。
 * 管理员可见（后端 RBAC 拦截，前端菜单同样仅管理员展示）。
 */
import { computed, onMounted, ref } from 'vue'
import {
  CheckCircleOutlined,
  CarryOutOutlined,
  ClockCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { api } from '../api/workflow'
import { useAuthStore } from '../stores/auth'
import { TASK_STATUS_META } from '../constants/status'
import DonutChart from '../components/charts/DonutChart.vue'

const auth = useAuthStore()
const overview = ref<{
  instanceCounts: Record<string, number>
  taskCounts: Record<string, number>
  activeInstances: number
  avgInstanceDurationMs: number | null
} | null>(null)
const bottlenecks = ref<Array<{ nodeName: string; count: number; avgStayMs: number }>>([])
const loading = ref(false)

const STATUS_LABELS: Record<string, string> = {
  running: '运行中',
  suspended: '已暂停',
  completed: '已完成',
  terminated: '已终止',
  canceled: '已撤回',
}
const STATUS_COLORS: Record<string, string> = {
  running: '#1677ff',
  suspended: '#faad14',
  completed: '#52c41a',
  terminated: '#ff4d4f',
  canceled: '#8c8c8c',
}

// 统计卡片配置（图标 + 主题色，视觉区分指标）
const statCards = computed(() => [
  { title: '运行中实例', value: overview.value?.activeInstances ?? 0, suffix: '', icon: ThunderboltOutlined, color: '#1677ff', bg: '#e6f4ff' },
  { title: '平均流转时长', value: overview.value?.avgInstanceDurationMs ?? 0, suffix: 'ms', icon: ClockCircleOutlined, color: '#722ed1', bg: '#f9f0ff' },
  { title: '已完成实例', value: overview.value?.instanceCounts?.['completed'] ?? 0, suffix: '', icon: CheckCircleOutlined, color: '#52c41a', bg: '#f6ffed' },
  { title: '任务总数', value: Object.values(overview.value?.taskCounts ?? {}).reduce((a, b) => a + b, 0), suffix: '', icon: CarryOutOutlined, color: '#fa8c16', bg: '#fff7e6' },
])

// 状态分布占比（环形图数据）
const instanceDistribution = computed(() =>
  Object.entries(overview.value?.instanceCounts ?? {}).map(([status, count]) => ({
    status,
    label: STATUS_LABELS[status] ?? status,
    count,
    color: STATUS_COLORS[status] ?? '#8c8c8c',
  })),
)

// 任务状态分布（环形图数据）
const taskDistribution = computed(() =>
  Object.entries(overview.value?.taskCounts ?? {}).map(([status, count]) => ({
    name: TASK_STATUS_META[status]?.label ?? status,
    value: count,
    color: { pending: '#1677ff', processing: '#13c2c2', approved: '#52c41a', rejected: '#ff4d4f', transferred: '#722ed1', canceled: '#8c8c8c', timeout_auto: '#fa8c16' }[status] ?? '#8c8c8c',
  })),
)

onMounted(async () => {
  if (!auth.roles.includes('admin')) return
  loading.value = true
  try {
    overview.value = await api.statsOverview()
    bottlenecks.value = await api.statsBottlenecks()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <a-spin :spinning="loading">
    <a-alert
      v-if="!auth.roles.includes('admin')"
      type="warning"
      message="监控看板仅管理员可见"
      show-icon
    />
    <template v-else>
      <!-- 统计卡片：图标着色 + 数值大字 -->
      <a-row :gutter="16">
        <a-col v-for="card in statCards" :key="card.title" :xs="12" :md="6" style="margin-bottom: 8px">
          <a-card>
            <div class="stat-card">
              <div class="stat-icon" :style="{ background: card.bg, color: card.color }">
                <component :is="card.icon" style="font-size: 22px" />
              </div>
              <div class="stat-body">
                <div class="stat-title">{{ card.title }}</div>
                <a-statistic
                  :value="card.value"
                  :suffix="card.suffix"
                  :value-style="{ fontSize: '24px', fontWeight: 600, color: card.color }"
                />
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <!-- 实例状态分布（环形图） -->
        <a-col :xs="24" :md="10" style="margin-bottom: 8px">
          <a-card title="实例状态分布">
            <DonutChart
              v-if="instanceDistribution.length"
              :data="instanceDistribution.map((d) => ({ name: d.label, value: d.count, color: d.color }))"
              height="240px"
            />
            <a-empty v-else description="暂无实例数据" />
          </a-card>
        </a-col>

        <!-- 节点瓶颈 -->
        <a-col :xs="24" :md="14" style="margin-bottom: 8px">
          <a-card title="节点瓶颈分析（平均停留时长 Top 10）">
            <a-table
              :data-source="bottlenecks"
              row-key="nodeName"
              size="small"
              :pagination="false"
              :scroll="{ x: 480 }"
              :columns="[
                { title: '节点', dataIndex: 'nodeName' },
                { title: '已完成任务数', dataIndex: 'count' },
                { title: '平均停留时长(ms)', dataIndex: 'avgStayMs' },
              ]"
            />
            <a-empty v-if="!bottlenecks.length" description="暂无数据" />
          </a-card>
        </a-col>
      </a-row>

      <!-- 任务状态分布（环形图） -->
      <a-card title="任务状态分布" style="margin-top: 8px">
        <DonutChart
          v-if="Object.keys(overview?.taskCounts ?? {}).length"
          :data="taskDistribution"
          height="240px"
        />
        <div v-if="!Object.keys(overview?.taskCounts ?? {}).length" style="text-align: center; padding: 16px 0">
          <a-empty description="暂无任务数据" />
        </div>
      </a-card>
    </template>
  </a-spin>
</template>

<style scoped>
.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-title {
  color: #8c8c8c;
  font-size: 13px;
  margin-bottom: 2px;
}
.dist-row {
  margin-bottom: 10px;
}
.dist-label {
  margin-bottom: 2px;
}
</style>
