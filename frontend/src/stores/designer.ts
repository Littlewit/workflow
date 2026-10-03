/**
 * 设计器状态（T6.3）：DSL 为唯一事实源 + Undo/Redo 快照栈。
 * 所有结构变更必须经 commit() 包装（对应编码计划 §6.2 Undo/Redo 方案）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { WfNode, WorkflowDSL } from '../types/workflow'

const MAX_HISTORY = 50 // 快照栈上限（防内存膨胀）

function emptyDsl(): WorkflowDSL {
  return {
    code: `wf_draft_${Math.random().toString(36).slice(2, 8)}`,
    name: '未命名流程',
    version: 0,
    variables: [],
    nodes: {
      start: { key: 'start', name: '发起', type: 'start', form_schema: {} },
      end: { key: 'end', name: '结束', type: 'end' },
    },
    edges: [{ source: 'start', target: 'end' }],
  }
}

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

export const useDesignerStore = defineStore('designer', () => {
  const dsl = ref<WorkflowDSL>(emptyDsl())
  const definitionId = ref('') // 已保存后回填
  const selectedKey = ref('')
  // 布局位置与 DSL 分离存储（后端不感知画布坐标）
  const layout = ref<Record<string, { x: number; y: number }>>({})

  const past = ref<WorkflowDSL[]>([])
  const future = ref<WorkflowDSL[]>([])
  // 结构版本号：驱动画布重渲染（避免深 watch 造成的循环）
  const version = ref(0)
  const canUndo = computed(() => past.value.length > 0)
  const canRedo = computed(() => future.value.length > 0)

  /** 结构变更统一入口：先压栈快照，再执行变更，最后版本 +1 触发重渲染。 */
  function commit(mutator: () => void) {
    past.value.push(clone(dsl.value))
    if (past.value.length > MAX_HISTORY) past.value.shift()
    future.value = []
    mutator()
    version.value++
  }

  function undo() {
    const prev = past.value.pop()
    if (!prev) return
    future.value.push(clone(dsl.value))
    dsl.value = prev
    version.value++
  }

  function redo() {
    const next = future.value.pop()
    if (!next) return
    past.value.push(clone(dsl.value))
    dsl.value = next
    version.value++
  }

  /** 加载既有 DSL（打开已保存定义）。 */
  function load(existing: { id: string; dsl: WorkflowDSL }) {
    definitionId.value = existing.id
    dsl.value = existing.dsl
    past.value = []
    future.value = []
    version.value++
  }

  /** 生成不冲突的节点 key。 */
  function nextKey(prefix: string): string {
    let i = 1
    while (`${prefix}_${i}` in dsl.value.nodes) i++
    return `${prefix}_${i}`
  }

  /** 添加节点：审批/抄送/网关（start/end 由初始 DSL 提供）。 */
  function addNode(type: 'approval' | 'cc' | 'exclusive_gateway') {
    const key = nextKey(type === 'exclusive_gateway' ? 'gateway' : type)
    let node: WfNode
    if (type === 'approval') {
      node = {
        key, name: '新审批节点', type,
        assignee: { mode: 'fixed_list', params: { user_ids: [] } },
        default_reject_target: null,
      }
    } else if (type === 'cc') {
      node = { key, name: '抄送', type, assignee: { mode: 'fixed_list', params: { user_ids: [] } } }
    } else {
      node = { key, name: '条件判断', type, branches: [], default_branch_key: 'default' }
    }
    commit(() => {
      dsl.value.nodes[key] = node
      // 新节点插在 end 之前：last -> new -> end
      const incoming = dsl.value.edges.find((e) => e.target === 'end')
      if (incoming) {
        dsl.value.edges = dsl.value.edges.filter((e) => e !== incoming)
        dsl.value.edges.push({ source: incoming.source, target: key })
      }
      dsl.value.edges.push({ source: key, target: 'end' })
      selectedKey.value = key
    })
  }

  /** 删除节点及其关联边（start/end 不可删）。 */
  function removeNode(key: string) {
    if (key === 'start' || key === 'end') return
    commit(() => {
      delete dsl.value.nodes[key]
      dsl.value.edges = dsl.value.edges.filter((e) => e.source !== key && e.target !== key)
      if (selectedKey.value === key) selectedKey.value = ''
    })
  }

  /** 更新节点属性（配置面板）。 */
  function updateNode(key: string, patch: Partial<WfNode>) {
    commit(() => {
      Object.assign(dsl.value.nodes[key], patch)
    })
  }

  /** 连线：在两节点间建立边（画布拖拽连线回调）。 */
  function connect(source: string, target: string) {
    if (source === target) return
    commit(() => {
      dsl.value.edges.push({ source, target })
    })
  }

  /** 断开连线。 */
  function disconnect(source: string, target: string) {
    commit(() => {
      dsl.value.edges = dsl.value.edges.filter(
        (e) => !(e.source === source && e.target === target),
      )
    })
  }

  return {
    dsl, definitionId, selectedKey, layout, version,
    canUndo, canRedo,
    commit, undo, redo, load, addNode, removeNode, updateNode, connect, disconnect,
  }
})
