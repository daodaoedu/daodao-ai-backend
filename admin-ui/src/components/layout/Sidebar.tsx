import { Link, useLocation } from 'react-router-dom'
import {
  BarChart3,
  FileText,
  List,
  LogOut,
  Cpu,
  MessageSquare,
  Users,
} from 'lucide-react'
import { useAuth } from '@/auth/AuthContext'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { to: '/query-logs', label: 'AI 查詢日誌', icon: List },
  { to: '/system-prompts', label: 'System Prompts', icon: FileText },
  { to: '/models', label: '模型管理', icon: Cpu },
  { to: '/user-quotas', label: 'Token 配額', icon: Users },
  { to: '/playground', label: 'Playground', icon: MessageSquare },
]

export function Sidebar() {
  const location = useLocation()
  const { logout } = useAuth()

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center px-4 border-b border-border">
        <span className="font-bold text-lg text-primary">DaoDao Admin</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-1">
        {navItems.map(({ to, label, icon: Icon }) => {
          const active = location.pathname === to
          return (
            <Link
              key={to}
              to={to}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors
                ${active
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-border p-2">
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          登出
        </button>
      </div>
    </aside>
  )
}
