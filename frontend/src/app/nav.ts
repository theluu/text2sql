import { type LucideIcon, MessageSquareText } from 'lucide-react'
import type { Role } from '@/features/auth/store'

export interface NavItem {
  to: '/'
  labelKey: string
  icon: LucideIcon
  minRole: Role
  exact?: boolean
}

export const NAV_ITEMS: NavItem[] = [{ to: '/', labelKey: 'nav.ask', icon: MessageSquareText, minRole: 'viewer' }]
