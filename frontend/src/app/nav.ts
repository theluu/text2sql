import { ClipboardCheck, FlaskConical, type LucideIcon, MessageSquareText } from 'lucide-react'
import type { Role } from '@/features/auth/store'

export interface NavItem {
  to: '/' | '/review' | '/eval'
  labelKey: string
  icon: LucideIcon
  minRole: Role
  badge?: 'review'
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.ask', icon: MessageSquareText, minRole: 'viewer' },
  { to: '/review', labelKey: 'nav.review', icon: ClipboardCheck, minRole: 'analyst', badge: 'review' },
  { to: '/eval', labelKey: 'nav.eval', icon: FlaskConical, minRole: 'analyst' },
]
