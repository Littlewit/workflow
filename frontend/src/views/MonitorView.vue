<script setup lang="ts">
/**
 * 监控看板（M7）：全局总览统计 + 节点瓶颈分析。
 * 管理员可见（后端 RBAC 拦截，前端菜单同样仅管理员展示）。
 */
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/workflow'
import { useAuthStore } from '../stores/auth'

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
const TASK_STATUS_COLORS: Record<string, string> = {
  pending: 'blue',
  processing: 'cyan',
  approved: 'green',
  rejected: 'red',
  transferred: 'purple',
  canceled: 'default',
  timeout_auto: 'orange',
}

// 状态分布占比（用于进度条展示）
const instanceDistribution = computed(() =>
  Object.entries(overview.value?.instanceCounts ?? {}).map(([status, count]) => {
    const total = Object.values(overview.value?.instanceCounts ?? {}).reduce((a, b) => a + b, 0)
    return {
      status,
      label: STATUS_LABELS[status] ?? status,
      count,
      percent: total ? Math.round((count / total) * 100) : 0,
    }
  }),
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
      <a-row :gutter="16">
        <a-col :xs="12" :md="6">
          <a-card><a-statistic title="运行中实例" :value="overview?.activeInstances ?? 0" /></a-card>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-card>
            <a-statistic
              title="平均流转时长"
              :value="overview?.avgInstanceDurationMs ?? 0"
              suffix="ms"
              :precision="0"
            />
          </a-card>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-card>
            <a-statistic
              title="实例总数"
              :value="Object.values(overview?.instanceCounts ?? {}).reduce((a, b) => a + b, 0)"
            />
          </a-card>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-card>
            <a-statistic
              title="任务总数"
              :value="Object.values(overview?.taskCounts ?? {}).reduce((a, b) => a + b, 0)"
            />
          </a-card>
        </a-col>
      </a-row>

      <a-card title="实例状态分布" style="margin-top: 16px">
        <div v-for="item in instanceDistribution" :key="item.status" style="margin-bottom: 10px">
          <div>{{ item.label }}（{{ item.count }}）</div>
          <a-progress :percent="item.percent" size="small" />
        </div>
        <a-empty v-if="!instanceDistribution.length" description="暂无实例数据" />
      </a-card>

      <a-card title="节点瓶颈分析（平均停留时长 Top 10）" style="margin-top: 16px">
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
      </a-card>

      <a-card title="任务状态分布" style="margin-top: 16px">
        <a-space wrap>
          <a-tag
            v-for="(count, status) in overview?.taskCounts ?? {}"
            :key="status"
            :color="TASK_STATUS_COLORS[status] ?? 'default'"
          >
            {{ status }}: {{ count }}
          </a-tag>
        </a-space>
        <div v-if="!Object.keys(overview?.taskCounts ?? {}).length" style="text-align: center; padding: 16px 0">
          <a-empty description="暂无任务数据" />
        </div>
      </a-card>
    </template>
  </a-spin>
</template>
