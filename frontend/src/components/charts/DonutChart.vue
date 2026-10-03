<script setup lang="ts">
/**
 * 环形图封装（ECharts 按需引入）：看板状态分布用。
 * 空数据时不渲染图表，由父组件展示空态。
 */
import { computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart } from 'echarts/charts'
import { LegendComponent, TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'

// 按需注册（只打包用到的能力）
use([CanvasRenderer, PieChart, TooltipComponent, LegendComponent])

const props = defineProps<{
  data: Array<{ name: string; value: number; color: string }>
  height?: string
}>()

const option = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
  legend: { bottom: '0', left: 'center', icon: 'circle', itemWidth: 10, itemHeight: 10 },
  series: [
    {
      type: 'pie',
      radius: ['45%', '70%'], // 环形：内空外实
      center: ['50%', '45%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 600, formatter: '{b}\n{d}%' },
      },
      data: props.data.map((d) => ({ name: d.name, value: d.value, itemStyle: { color: d.color } })),
    },
  ],
}))
</script>

<template>
  <VChart class="chart" :option="option" autoresize :style="{ height: height ?? '260px' }" />
</template>
