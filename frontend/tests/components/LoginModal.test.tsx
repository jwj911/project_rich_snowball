import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import LoginModal from '@/components/auth/LoginModal'
import { AuthProvider } from '@/components/auth/AuthProvider'

vi.mock('@/lib/api', () => ({
  api: {
    getToken: vi.fn(() => null),
    logout: vi.fn(),
    login: vi.fn(),
    getCurrentUser: vi.fn(),
  },
}))

describe('LoginModal A11y', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function renderModal() {
    const onClose = vi.fn()
    const onSuccess = vi.fn()
    const onSwitchToRegister = vi.fn()

    render(
      <AuthProvider>
        <button type="button" data-testid="trigger">登录</button>
        <LoginModal
          onClose={onClose}
          onSuccess={onSuccess}
          onSwitchToRegister={onSwitchToRegister}
        />
      </AuthProvider>,
    )

    return { onClose, onSuccess, onSwitchToRegister }
  }

  it('focuses the autofocus element on open', () => {
    renderModal()
    const usernameInput = screen.getByLabelText('用户名')
    expect(usernameInput).toHaveFocus()
  })

  it('traps Tab focus within the dialog', () => {
    renderModal()

    const dialog = screen.getByRole('dialog')
    const focusableElements = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('aria-hidden'))
    const first = focusableElements[0]
    const last = focusableElements[focusableElements.length - 1]

    // Focus on last element, press Tab → should go to first
    last.focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(first)
  })

  it('traps Shift+Tab focus within the dialog', () => {
    renderModal()

    const dialog = screen.getByRole('dialog')
    const focusableElements = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('aria-hidden'))
    const first = focusableElements[0]
    const last = focusableElements[focusableElements.length - 1]

    // Focus on first element, press Shift+Tab → should go to last
    first.focus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })

  it('closes on Escape key', () => {
    const { onClose } = renderModal()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('has dialog role and aria-modal', () => {
    renderModal()
    const dialog = screen.getByRole('dialog', { name: '登录' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('has visible labels for all inputs', () => {
    renderModal()
    expect(screen.getByLabelText('用户名')).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
  })
})
