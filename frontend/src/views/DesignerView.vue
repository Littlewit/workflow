<script setup lang="ts">
/**
 * 流程设计器（T6.2 MVP）：LogicFlow 画布 + 缩放工具。
 * 节点面板/配置面板/校验器在 T6.2 后续小步交付。
 */
import { onMounted, ref } from 'vue'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/lib/index.css'

const container = ref<HTMLDivElement>()
let lf: LogicFlow | null = null

onMounted(() => {
  if (!container.value) return
  lf = new LogicFlow({ container: container.value, grid: true })
  lf.render({
    // 演示用最小流程：start -> approval -> end
    nodes: [
      { id: 'start', type: 'circle', x: 100, y: 150, text: '发起' },
      { id: 'a1', type: 'rect', x: 320, y: 150, text: '部门审批' },
      { id: 'end', type: 'circle', x: 540, y: 150, text: '结束' },
    ],
    edges: [
      { sourceNodeId: 'start', targetNodeId: 'a1', type: 'polyline' },
      { sourceNodeId: 'a1', targetNodeId: 'end', type: 'polyline' },
    ],
  })
})
</script>

<template>
  <div>
    <a-space style="margin-bottom: 12px">
      <a-button @click="lf?.zoom(true)">放大</a-button>
      <a-button @click="lf?.zoom(false)">缩小</a-button>
    </a-space>
    <div ref="container" style="height: 560px; border: 1px solid #eee"></div>
  </div>
</template>
