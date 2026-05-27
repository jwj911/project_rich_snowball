import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import RegisterModal from '@/components/auth/RegisterModal'
import { AuthProvider } from '@/components/auth/AuthProvider'

vi.mock('@/lib/api', () => ({
  api: {
    getToken: vi.fn(() => null),
    logout: vi.fn(),
    login: vi.fn(),
    getCurrentUser: vi.fn(),
  },
}))

describe('RegisterModal A11y', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function renderModal() {
    const onClose = vi.fn()
    const onSuccess = vi.fn()

    render(
      <AuthProvider>
        <button type="button" data-testid="trigger">注册</button>
        <RegisterModal onClose={onClose} onSuccess={onSuccess} />
      </AuthProvider>,
    )

    return { onClose, onSuccess }
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
    const dialog = screen.getByRole('dialog', { name: '注册' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('has visible labels for all inputs', () => {
    renderModal()
    expect(screen.getByLabelText('用户名')).toBeInTheDocument()
    expect(screen.getByLabelText('邮箱')).toBeInTheDocument()
    expect(screen.getByLabelText('密码')).toBeInTheDocument()
  })
})
