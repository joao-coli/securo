import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'

import { TransactionDialog } from '@/components/transaction-dialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import { createTestQueryClient, renderWithProviders, t } from '@/test/utils'

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'BRL' } } }),
}))
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ current: { id: 'workspace-1' }, hasModule: () => true }),
}))

function renderCreation() {
  const queryClient = createTestQueryClient()
  queryClient.setDefaultOptions({ queries: { enabled: false, retry: false } })
  queryClient.setQueryData(['funding-domains', 'workspace-1'], [{
    id: 'domain-1', name: 'Household', icon: 'home', color: '#112233', is_active: true,
  }])
  const onSave = vi.fn()
  const view = renderWithProviders(
    <TooltipProvider>
      <TransactionDialog
        open onClose={vi.fn()} transaction={null} categories={[]} categoryGroups={[]}
        accounts={[{ id: 'card-1', name: 'Card', type: 'credit_card' }]}
        duplicateDraft={{
          account_id: 'card-1', description: 'Household purchase', amount: 50,
          date: '2026-09-07', type: 'debit', currency: 'BRL', funding_domain_id: 'domain-1',
        }}
        onSave={onSave} loading={false} error={null}
      />
    </TooltipProvider>,
    { queryClient },
  )
  return { ...view, onSave }
}

describe('funding domain during transaction creation', () => {
  it('passes the selected domain through the installment option', async () => {
    const { user, onSave } = renderCreation()
    await user.click(screen.getByRole('checkbox', { name: t('transactions.makeInstallment') }))
    await user.click(screen.getByRole('button', { name: t('common.save') }))
    expect(onSave).toHaveBeenCalledOnce()
    expect(onSave.mock.calls[0][2].base.funding_domain_id).toBe('domain-1')
  })

  it('keeps the selected domain when the recurring option is enabled', async () => {
    const { user, onSave } = renderCreation()
    await user.click(screen.getByRole('checkbox', { name: t('transactions.makeRecurring') }))
    await user.click(screen.getByRole('button', { name: t('common.save') }))
    expect(onSave).toHaveBeenCalledOnce()
    expect(onSave.mock.calls[0][0].funding_domain_id).toBe('domain-1')
    expect(onSave.mock.calls[0][1]).toMatchObject({ frequency: 'monthly' })
  })
})
