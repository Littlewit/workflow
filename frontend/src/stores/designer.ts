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

  /** 选中态一致性：撤销/重做后若选中节点已不存在则清除。 */
  function syncSelectedKey() {
    if (store_selected_missing()) selectedKey.value = ''
  }
  function store_selected_missing(): boolean {
    return selectedKey.value !== '' && !(selectedKey.value in dsl.value.nodes)
  }

  /** 结构变更统一入口：先压栈快照，再执行变更（异常则回滚快照），最后版本 +1。 */
  function commit(mutator: () => void) {
    past.value.push(clone(dsl.value))
    if (past.value.length > MAX_HISTORY) past.value.shift() // 栈上限，防内存膨胀
    try {
      mutator()
    } catch (err) {
      past.value.pop() // 变更失败：快照不入栈，保持撤销语义一致
      throw err
    }
    future.value = []
    version.value++
    syncSelectedKey()
  }

  function undo() {
    const prev = past.value.pop()
    if (!prev) return
    future.value.push(clone(dsl.value))
    dsl.value = prev
    version.value++
    syncSelectedKey()
  }

  function redo() {
    const next = future.value.pop()
    if (!next) return
    past.value.push(clone(dsl.value))
    dsl.value = next
    version.value++
    syncSelectedKey()
  }

  /** 加载既有 DSL（打开已保存定义）：清空历史与画布残留状态。 */
  function load(existing: { id: string; dsl: WorkflowDSL }) {
    definitionId.value = existing.id
    dsl.value = existing.dsl
    past.value = []
    future.value = []
    selectedKey.value = ''
    layout.value = {}
    version.value++
  }

  /** 生成不冲突的节点 key。 */
  function nextKey(prefix: string): string {
    let i = 1
    while (`${prefix}_${i}` in dsl.value.nodes) i++
    return `${prefix}_${i}`
  }

  /**
   * 自动布局（结构变化后调用）：按"从 start 出发的最长路径深度"分层，
   * 同层节点垂直居中错开（分支呈现为并行泳道），x 按深度递增。
   * 效果：网关的分支节点垂直并列，end 固定在最右。
   */
  function autoLayout() {
    const nodes = dsl.value.nodes
    const nodeKeys = Object.keys(nodes)
    const startKey = nodeKeys.find((k) => nodes[k].type === 'start')

    // 出边表
    const out = new Map<string, string[]>()
    for (const e of dsl.value.edges) {
      out.set(e.source, [...(out.get(e.source) ?? []), e.target])
    }

    // 深度 = 最长路径（多轮松弛，兼容少量环；不可达节点深度按可达最大值+1 追加）
    const depth = new Map<string, number>()
    if (startKey) depth.set(startKey, 0)
    for (let round = 0; round < nodeKeys.length; round++) {
      for (const [src, targets] of out) {
        const d = depth.get(src)
        if (d === undefined) continue
        for (const t of targets) {
          if ((depth.get(t) ?? -1) < d + 1) depth.set(t, d + 1)
        }
      }
    }
    // 不可达节点：深度 = 已知最大深度 + 1
    const maxKnown = Math.max(-1, ...depth.values())
    for (const k of nodeKeys) {
      if (!depth.has(k)) depth.set(k, maxKnown + 1)
    }
    // end 节点固定排最后一列（分支汇合点视觉收敛）
    const endKey = nodeKeys.find((k) => nodes[k].type === 'end')
    if (endKey) {
      const maxDepth = Math.max(-1, ...[...depth.values()])
      depth.set(endKey, maxDepth + 1)
    }

    // 分层分组：同层节点垂直居中排布
    const levels = new Map<number, string[]>()
    for (const k of nodeKeys) {
      const d = depth.get(k) ?? 0
      levels.set(d, [...(levels.get(d) ?? []), k])
    }

    const next: Record<string, { x: number; y: number }> = {}
    for (const [d, keys] of levels) {
      keys.forEach((k, i) => {
        // 同层多节点时垂直对称错开（层间距 110）
        const offsetY = (i - (keys.length - 1) / 2) * 110
        next[k] = { x: 120 + d * 180, y: 200 + offsetY }
      })
    }
    layout.value = next
  }

  /**
   * 添加节点：
   * - 选中了节点 → 插到选中节点之后（普通节点改写其唯一出边形成链；
   *   网关则追加一条新分支边，可连续多次添加多个分支节点）
   * - 未选中 → 插到 end 之前
   */
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
      const sel = selectedKey.value
      if (sel && sel in dsl.value.nodes && sel !== key) {
        const selNode = dsl.value.nodes[sel]
        if (selNode.type === 'exclusive_gateway') {
          // 网关：每次添加都是追加一个分支（gw→new→end），既有分支不动
          dsl.value.edges.push({ source: sel, target: key })
          dsl.value.edges.push({ source: key, target: 'end' })
        } else {
          // 普通节点：唯一出边 sel→X 改写为 sel→new→X（链式插入）
          const outEdge = dsl.value.edges.find((e) => e.source === sel)
          const next = outEdge?.target
          dsl.value.edges = dsl.value.edges.filter((e) => e !== outEdge)
          dsl.value.edges.push({ source: sel, target: key })
          if (next) dsl.value.edges.push({ source: key, target: next })
        }
      } else {
        // 未选中：插到 end 之前
        const incoming = dsl.value.edges.find((e) => e.target === 'end')
        if (incoming) {
          dsl.value.edges = dsl.value.edges.filter((e) => e !== incoming)
          dsl.value.edges.push({ source: incoming.source, target: key })
        }
        dsl.value.edges.push({ source: key, target: 'end' })
      }
      selectedKey.value = key
      autoLayout() // 结构变化后自动平铺
    })
  }

  /** 删除节点及其关联边（start/end 不可删）。 */
  function removeNode(key: string) {
    if (key === 'start' || key === 'end') return
    commit(() => {
      delete dsl.value.nodes[key]
      dsl.value.edges = dsl.value.edges.filter((e) => e.source !== key && e.target !== key)
      if (selectedKey.value === key) selectedKey.value = ''
      autoLayout() // 删除后同样重新平铺，消除空洞
    })
  }

  /** 更新节点属性（配置面板）；key 不存在时静默忽略（与画布状态解耦）。 */
  function updateNode(key: string, patch: Partial<WfNode>) {
    if (!(key in dsl.value.nodes)) return
    commit(() => {
      Object.assign(dsl.value.nodes[key], patch)
    })
  }

  /** 连线：在两节点间建立边（画布拖拽连线回调）；重复边忽略。 */
  function connect(source: string, target: string) {
    if (source === target) return
    const exists = dsl.value.edges.some((e) => e.source === source && e.target === target)
    if (exists) return
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
