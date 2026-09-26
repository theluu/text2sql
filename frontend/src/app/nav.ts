import { Activity, ClipboardCheck, FlaskConical, type LucideIcon, MessageSquareText, SlidersHorizontal } from 'lucide-react'
import type { Role } from '@/features/auth/store'

export interface NavItem {
  to: '/' | '/review' | '/eval' | '/ops' | '/admin'
  labelKey: string
  icon: LucideIcon
  minRole: Role
  badge?: 'review'
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.ask', icon: MessageSquareText, minRole: 'viewer' },
  { to: '/review', labelKey: 'nav.review', icon: ClipboardCheck, minRole: 'analyst', badge: 'review' },
  { to: '/eval', labelKey: 'nav.eval', icon: FlaskConical, minRole: 'analyst' },
  { to: '/ops', labelKey: 'nav.ops', icon: Activity, minRole: 'admin' },
  { to: '/admin', labelKey: 'nav.settings', icon: SlidersHorizontal, minRole: 'admin' },
]
