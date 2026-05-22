export interface ApiTransport {
  requestRaw(url: string, options?: RequestInit): Promise<Response>
  request<T>(url: string, options?: RequestInit): Promise<T>
}

export function parseHeaderNumber(headers: Headers, name: string) {
  const value = Number.parseInt(headers.get(name) || '0', 10)
  return Number.isFinite(value) ? value : 0
}
