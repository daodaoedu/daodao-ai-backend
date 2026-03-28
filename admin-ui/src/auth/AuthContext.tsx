import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { TOKEN_KEY } from '@/api/client'
import { ping } from '@/api/admin'

interface AuthContextValue {
  isAuthenticated: boolean
  login: (token: string) => Promise<boolean>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  login: async () => false,
  logout: () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => !!localStorage.getItem(TOKEN_KEY)
  )

  const login = useCallback(async (token: string): Promise<boolean> => {
    localStorage.setItem(TOKEN_KEY, token)
    try {
      await ping()
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
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
