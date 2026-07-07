/**
 * Declares the mapping from shadcn CSS variable names to VMS design-system tokens.
 * Every value must start with "var(--" — no literal colors allowed.
 * Used by shadcn-compat.test.ts to assert the compat layer is not drifting.
 */
export const SHADCN_VAR_MAP = Object.freeze({
  '--background':              'var(--surface-base)',
  '--foreground':              'var(--text-primary)',
  '--card':                    'var(--surface-base)',
  '--card-foreground':         'var(--text-primary)',
  '--popover':                 'var(--surface-base)',
  '--popover-foreground':      'var(--text-primary)',
  '--muted':                   'var(--surface-sunken)',
  '--muted-foreground':        'var(--text-muted)',
  '--accent':                  'var(--surface-raised)',
  '--accent-foreground':       'var(--text-primary)',
  '--border':                  'var(--border-default)',
  '--input':                   'var(--border-default)',
  '--ring':                    'var(--interactive-primary)',
  '--primary':                 'var(--interactive-primary)',
  '--primary-foreground':      'var(--text-inverse)',
  '--secondary':               'var(--surface-sunken)',
  '--secondary-foreground':    'var(--text-primary)',
  '--destructive':             'var(--destructive)',
  '--destructive-foreground':  'var(--text-inverse)',
} as const)

/** All shadcn vars that need to be present in the compat layer. */
export const REQUIRED_SHADCN_VARS = Object.keys(SHADCN_VAR_MAP) as Array<
  keyof typeof SHADCN_VAR_MAP
>
