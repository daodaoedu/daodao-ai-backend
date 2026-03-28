import axios from 'axios'

export const TOKEN_KEY = 'daodao_admin_token'

const apiClient = axios.create({
  baseURL: '/',
  timeout: 30000,
})

// JWT 自動注入
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 403 自動登出
apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 403) {
      localStorage.removeItem(TOKEN_KEY)
      window.location.href = '/admin/login'
    }
    return Promise.reject(err)
  }
)

export default apiClient
