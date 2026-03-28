import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { TOKEN_KEY } from '@/api/client'
import { ping } from '@/api/admin'

interface AdminInfo {
  adminId: number
  adminNickname: string | null
}

interface AuthContextValue {
  isAuthenticated: boolean
  adminInfo: AdminInfo | null
  login: (token: string) => Promise<boolean>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  adminInfo: null,
  login: async () => false,
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => !!localStorage.getItem(TOKEN_KEY)
  )
  const [adminInfo, setAdminInfo] = useState<AdminInfo | null>(null)

  // 頁面重整後重新取得 admin 資訊（token 仍存在但 adminInfo 為 null）
  useEffect(() => {
    if (!localStorage.getItem(TOKEN_KEY)) return
    ping()
      .then((res) => {
        const d = res.data.data
        setAdminInfo({ adminId: d.admin_id, adminNickname: d.nickname })
        setIsAuthenticated(true)
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
        setIsAuthenticated(false)
      })
  }, [])

  const login = useCallback(async (token: string): Promise<boolean> => {
    localStorage.setItem(TOKEN_KEY, token)
    try {
      const res = await ping()
      const d = res.data.data
      setAdminInfo({ adminId: d.admin_id, adminNickname: d.nickname })
      setIsAuthenticated(true)
      return true
    } catch {
      localStorage.removeItem(TOKEN_KEY)
      setIsAuthenticated(false)
      return false
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setIsAuthenticated(false)
    setAdminInfo(null)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, adminInfo, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
