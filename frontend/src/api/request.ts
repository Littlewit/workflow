/**
 * HTTP 请求封装：统一处理响应包裹、错误码与 409 冲突提示。
 * 响应拦截器已解包 ApiResponse.data，导出的 get/post 直接返回业务数据。
 * 对应详细设计 §8.2 "冲突处理"：42100/43102 自动提示"状态已变化"。
 */
import axios from 'axios'
import { message } from 'ant-design-vue'
import { useAuthStore } from '../stores/auth'

const http = axios.create({ baseURL: '/api/v1', timeout: 15000 })

// 请求拦截：附加 JWT
http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

// 响应拦截：业务码非 0 统一报错；401 跳登录
http.interceptors.response.use(
  (resp) => {
    const body = resp.data as { code: number; message: string; data: unknown }
    if (body.code !== 0) {
      if (body.code === 42100 || body.code === 43102) {
        // 冲突类错误：前端并未自动刷新数据，提示语必须与实际行为一致
        message.warning('状态已被其他操作变更，请刷新页面后重试')
      } else {
        message.error(`${body.message}（${body.code}）`)
      }
      return Promise.reject(body)
    }
    // 解包：后续调用拿到的是 data 本身（类型断言见 get/post 封装）
    return body.data as unknown as typeof resp.data
  },
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      useAuthStore().logout()
      message.error('登录已失效，请重新登录')
      window.location.hash = '#/login'
    } else {
      message.error(error.response?.data?.message ?? '网络异常')
    }
    return Promise.reject(error)
  },
)

export default {
  /** GET 请求：T 为解包后的业务数据类型。 */
  async get<T>(url: string): Promise<T> {
    return (await http.get(url)) as T
  },
  /** POST 请求：T 为解包后的业务数据类型。 */
  async post<T>(url: string, data?: unknown): Promise<T> {
    return (await http.post(url, data)) as T
  },
  /** PUT 请求：T 为解包后的业务数据类型。 */
  async put<T>(url: string, data?: unknown): Promise<T> {
    return (await http.put(url, data)) as T
  },
}
