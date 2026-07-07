import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Helmet } from 'react-helmet-async'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Button } from '@/shared/design-system/components/Button'
import { Input } from '@/shared/design-system/components/Input'
import { UnauthorizedError } from '@/shared/api/errors'

const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { login, isLoading, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const nextPath = params.get('next') ?? '/'

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  useEffect(() => {
    if (isAuthenticated) navigate(nextPath, { replace: true })
  }, [isAuthenticated, navigate, nextPath])

  const onSubmit = async (values: LoginFormValues) => {
    try {
      await login(values.username, values.password)
      // navigation handled by the useEffect above once token lands in store
    } catch (err) {
      const message =
        err instanceof UnauthorizedError
          ? 'Invalid username or password.'
          : 'An unexpected error occurred.'
      setError('root', { message })
    }
  }

  return (
    <>
      <Helmet title="Log in" />
      <div className="flex min-h-screen items-center justify-center bg-surface-sunken px-4">
        <div className="w-full max-w-[400px] rounded-xl bg-surface-base p-8 shadow-3 border-t-[3px] border-[var(--brand-accent)]">
          {/* Logo / wordmark */}
          <div className="mb-8 text-center">
            <ShieldCheck
              size={24}
              className="mx-auto mb-3 text-[var(--brand-accent)]"
              aria-hidden
            />
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">
              Video Management System
            </p>
            <h1 className="mt-1 font-display text-[28px] font-bold text-text-primary">VMS</h1>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
            <Input
              label="Username"
              autoComplete="username"
              autoFocus
              error={errors.username?.message}
              {...register('username')}
            />
            <Input
              label="Password"
              type="password"
              autoComplete="current-password"
              error={errors.password?.message}
              {...register('password')}
            />

            {errors.root && (
              <p role="alert" className="text-[13px] text-[var(--error)]">
                {errors.root.message}
              </p>
            )}

            <Button type="submit" loading={isLoading} className="mt-2 w-full">
              Log in
            </Button>
          </form>
        </div>
      </div>
    </>
  )
}
