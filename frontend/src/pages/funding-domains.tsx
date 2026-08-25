import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fundingDomains as fundingDomainsApi } from '@/lib/api'
import { invalidateFinancialQueries } from '@/lib/invalidate-queries'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { PageHeader } from '@/components/page-header'
import { CategoryIcon } from '@/components/category-icon'
import { IconPicker } from '@/components/icon-picker'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/contexts/workspace-context'
import { Archive, Pencil, Plus, RotateCcw, Search } from 'lucide-react'
import type { FundingDomain, FundingDomainCreate, FundingDomainUpdate } from '@/types'

const DEFAULT_ICON = 'wallet'
const DEFAULT_COLOR = '#6B7280'

export default function FundingDomainsPage() {
  const { t } = useTranslation()
  const { current } = useWorkspace()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingDomain, setEditingDomain] = useState<FundingDomain | null>(null)
  const [formIcon, setFormIcon] = useState(DEFAULT_ICON)
  const [formColor, setFormColor] = useState(DEFAULT_COLOR)

  const { data: domainsList, isLoading } = useQuery({
    queryKey: ['funding-domains', current?.id, { includeInactive }],
    queryFn: () => fundingDomainsApi.list(includeInactive),
    enabled: Boolean(current?.id),
  })

  const invalidateDomains = () => {
    queryClient.invalidateQueries({ queryKey: ['funding-domains'] })
  }

  const createMutation = useMutation({
    mutationFn: (domain: FundingDomainCreate) => fundingDomainsApi.create(domain),
    onSuccess: () => {
      invalidateDomains()
      setDialogOpen(false)
      toast.success(t('fundingDomains.created'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, ...domain }: FundingDomainUpdate & { id: string }) =>
      fundingDomainsApi.update(id, domain),
    onSuccess: () => {
      invalidateDomains()
      invalidateFinancialQueries(queryClient)
      setDialogOpen(false)
      setEditingDomain(null)
      toast.success(t('fundingDomains.updated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => fundingDomainsApi.delete(id),
    onSuccess: () => {
      invalidateDomains()
      invalidateFinancialQueries(queryClient)
      toast.success(t('fundingDomains.deactivated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const reactivateMutation = useMutation({
    mutationFn: (id: string) => fundingDomainsApi.update(id, { is_active: true }),
    onSuccess: () => {
      invalidateDomains()
      invalidateFinancialQueries(queryClient)
      toast.success(t('fundingDomains.reactivated'))
    },
    onError: () => toast.error(t('common.error')),
  })

  const openCreate = () => {
    setEditingDomain(null)
    setFormIcon(DEFAULT_ICON)
    setFormColor(DEFAULT_COLOR)
    setDialogOpen(true)
  }

  const openEdit = (domain: FundingDomain) => {
    setEditingDomain(domain)
    setFormIcon(domain.icon || DEFAULT_ICON)
    setFormColor(domain.color || DEFAULT_COLOR)
    setDialogOpen(true)
  }

  const filteredDomains = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()
    return (domainsList ?? []).filter((domain) => {
      if (!normalizedSearch) return true
      return (
        domain.name.toLowerCase().includes(normalizedSearch) ||
        (domain.description ?? '').toLowerCase().includes(normalizedSearch)
      )
    })
  }, [domainsList, search])

  return (
    <div>
      <PageHeader
        section={t('fundingDomains.section')}
        title={t('fundingDomains.title')}
        action={
          <Button size="sm" className="gap-1.5 h-8" onClick={openCreate}>
            <Plus size={13} />
            <span>{t('fundingDomains.add')}</span>
          </Button>
        }
      />

      <div className="bg-card rounded-xl border border-border shadow-sm p-3 md:p-4 mb-4">
        <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
          <div className="relative w-full md:w-[340px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={16} />
            <Input
              type="text"
              placeholder={t('fundingDomains.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 h-[38px] text-sm"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="h-4 w-4 rounded border-border accent-primary"
            />
            {t('fundingDomains.showInactive')}
          </label>
        </div>
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-6 space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        ) : filteredDomains.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-10">
            {t('fundingDomains.empty')}
          </p>
        ) : (
          <div className="divide-y divide-border">
            {filteredDomains.map((domain) => (
              <div
                key={domain.id}
                className={cn(
                  'flex items-center gap-3 px-4 sm:px-5 py-3 hover:bg-muted transition-colors',
                  !domain.is_active && 'opacity-70',
                )}
              >
                <CategoryIcon icon={domain.icon} color={domain.color} size="md" />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-foreground truncate">{domain.name}</p>
                    {!domain.is_active && (
                      <span className="text-[10px] font-semibold bg-muted text-muted-foreground px-1.5 py-0 rounded-full">
                        {t('fundingDomains.inactive')}
                      </span>
                    )}
                  </div>
                  {domain.description && (
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{domain.description}</p>
                  )}
                </div>
                <div className="hidden sm:flex items-center gap-2 shrink-0">
                  <span className="inline-block w-3.5 h-3.5 rounded-full border border-black/10" style={{ backgroundColor: domain.color }} />
                  <span className="text-xs text-muted-foreground font-mono">{domain.color}</span>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    className="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/5 transition-colors"
                    onClick={() => openEdit(domain)}
                    title={t('common.edit')}
                  >
                    <Pencil size={13} />
                  </button>
                  {domain.is_active ? (
                    <button
                      className="p-1.5 rounded-md text-muted-foreground hover:text-amber-600 hover:bg-amber-50 transition-colors"
                      onClick={() => deactivateMutation.mutate(domain.id)}
                      disabled={deactivateMutation.isPending}
                      title={t('fundingDomains.deactivate')}
                    >
                      <Archive size={13} />
                    </button>
                  ) : (
                    <button
                      className="p-1.5 rounded-md text-muted-foreground hover:text-emerald-600 hover:bg-emerald-50 transition-colors"
                      onClick={() => reactivateMutation.mutate(domain.id)}
                      disabled={reactivateMutation.isPending}
                      title={t('fundingDomains.reactivate')}
                    >
                      <RotateCcw size={13} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog open={dialogOpen} onOpenChange={() => { setDialogOpen(false); setEditingDomain(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingDomain ? t('fundingDomains.edit') : t('fundingDomains.new')}</DialogTitle>
          </DialogHeader>
          <form
            key={editingDomain?.id ?? 'new'}
            onSubmit={(event) => {
              event.preventDefault()
              const formData = new FormData(event.currentTarget)
              const payload = {
                name: formData.get('name') as string,
                icon: formData.get('icon') as string,
                color: formData.get('color') as string,
                description: (formData.get('description') as string).trim() || null,
              }
              if (editingDomain) {
                updateMutation.mutate({ id: editingDomain.id, ...payload })
              } else {
                createMutation.mutate(payload)
              }
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label>{t('fundingDomains.name')}</Label>
              <Input name="name" defaultValue={editingDomain?.name ?? ''} required />
            </div>
            <div className="space-y-2">
              <Label>{t('fundingDomains.description')}</Label>
              <Input name="description" defaultValue={editingDomain?.description ?? ''} placeholder={t('fundingDomains.descriptionPlaceholder')} />
            </div>
            <div className="space-y-2">
              <Label>{t('groups.color')}</Label>
              <Input name="color" type="color" value={formColor} onChange={(e) => setFormColor(e.target.value)} required className="h-9 px-2 py-1" />
            </div>
            <div className="space-y-2">
              <Label>{t('groups.icon')}</Label>
              <IconPicker value={formIcon} color={formColor} onChange={setFormIcon} />
              <input type="hidden" name="icon" value={formIcon} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => { setDialogOpen(false); setEditingDomain(null) }}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                {t('common.save')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
