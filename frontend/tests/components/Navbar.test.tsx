import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Navbar from '@/components/Navbar'

const authState = {
  user: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
}))

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => authState,
}))

describe('Navbar auth dialog', () => {
  afterEach(() => {
    authState.user = null
    authState.login.mockReset()
    authState.register.mockReset()
    authState.logout.mockReset()
  })

  it('opens login as an accessible dialog and closes with Escape', async () => {
    render(<Navbar />)

    const trigger = screen.getAllByRole('button', { name: /登录/ })[0]
    trigger.focus()
    fireEvent.click(trigger)

    const dialog = screen.getByRole('dialog', { name: '登录' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('用户名')).toHaveFocus()

    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(trigger).toHaveFocus()
  })

  it('switches between login and register without leaving the dialog layer', () => {
    render(<Navbar />)

    fireEvent.click(screen.getAllByRole('button', { name: /登录/ })[0])
    fireEvent.click(within(screen.getByRole('dialog', { name: '登录' })).getByRole('button', { name: '注册' }))

    expect(screen.getByRole('dialog', { name: '注册' })).toBeInTheDocument()
    expect(screen.getByLabelText('邮箱')).toBeInTheDocument()

    fireEvent.click(within(screen.getByRole('dialog', { name: '注册' })).getByRole('button', { name: '去登录' }))

    expect(screen.getByRole('dialog', { name: '登录' })).toBeInTheDocument()
  })

  it('opens the login dialog from the global auth event', () => {
    render(<Navbar />)

    fireEvent(window, new Event('open-login-modal'))

    expect(screen.getByRole('dialog', { name: '登录' })).toBeInTheDocument()
  })
})
