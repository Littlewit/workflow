/** 统一响应包裹类型（对应后端 app/api/response.py）。 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
  traceId: string
}
