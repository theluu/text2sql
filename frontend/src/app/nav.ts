import { type LucideIcon, MessageSquareText, ClipboardCheck } from 'lucide-react'
import type { Role } from '@/features/auth/store'

export interface NavItem {
  to: '/' | '/review'
  labelKey: string
  icon: LucideIcon
  minRole: Role
  badge?: 'review'
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.ask', icon: MessageSquareText, minRole: 'viewer' },
  { to: '/review', labelKey: 'nav.review', icon: ClipboardCheck, minRole: 'analyst', badge: 'review' },
]
