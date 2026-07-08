import * as React from 'react'
import type { CSSProperties } from 'react'
import { SkeletonChart } from '@/shared/design-system/components/Skeleton'

const ReactECharts = React.lazy(() => import('echarts-for-react'))

interface EChartsWrapperProps {
  option: object
  style?: CSSProperties
  className?: string
}

/** Lazy ECharts wrapper with SkeletonChart fallback. §V.2 */
export function EChartsWrapper({ option, style, className }: EChartsWrapperProps) {
  return (
    <React.Suspense fallback={<SkeletonChart className={className} style={style} />}>
      <ReactECharts option={option} style={style} notMerge lazyUpdate className={className} />
    </React.Suspense>
  )
}

/** Read CSS variable theme tokens for ECharts axis/grid styling. */
export function useChartTheme() {
  return React.useMemo(() => {
    const style = typeof document !== 'undefined' ? getComputedStyle(document.body) : null
    const get = (v: string, fallback: string) => style?.getPropertyValue(v).trim() || fallback
    return {
      textColor: get('--text-primary', '#e2e8f0'),
      mutedColor: get('--text-muted', '#64748b'),
      borderColor: get('--border-default', '#1e293b'),
      backgroundColor: get('--surface-raised', '#1a2234'),
    }
  }, [])
}
