import { type APIRequestContext, type Browser, expect, type Page } from '@playwright/test'

export const PASSWORD = 'demo1234'

export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/login')
  await page.evaluate(() => localStorage.setItem('t2s-lang', 'vi'))
  await page.reload()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Bạn muốn biết điều gì hôm nay?' })).toBeVisible()
}

export async function newSession(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await signIn(page, email)
  return page
}

export async function ask(page: Page, question: string): Promise<void> {
  const box = page.getByLabel(/Hỏi về doanh thu/)
  await box.fill(question)
  await box.press('Enter')
}

export async function adminToken(request: APIRequestContext): Promise<string> {
  const response = await request.post('/api/auth/login', { data: { email: 'admin@demo.vn', password: PASSWORD } })
  return (await response.json()).access_token as string
}
