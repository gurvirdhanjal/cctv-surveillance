import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { createRef } from 'react'
import { Box, Stack, Cluster, Surface } from './index'

// §G spacing scale — only these values are legal gap/padding props
const VALID_GAPS = [2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96] as const

describe('Box', () => {
  it('renders a div by default', () => {
    const { container } = render(<Box>hello</Box>)
    expect(container.firstElementChild?.tagName).toBe('DIV')
  })

  it('forwards className', () => {
    const { container } = render(<Box className="custom-class">x</Box>)
    expect(container.firstElementChild?.classList).toContain('custom-class')
  })

  it('renders children', () => {
    const { getByText } = render(<Box>content</Box>)
    expect(getByText('content')).toBeTruthy()
  })

  it('forwards ref to underlying element', () => {
    const ref = createRef<HTMLDivElement>()
    render(<Box ref={ref}>x</Box>)
    expect(ref.current).toBeTruthy()
    expect(ref.current?.tagName).toBe('DIV')
  })

  it('renders as a different element via as prop', () => {
    const { container } = render(<Box as="section">x</Box>)
    expect(container.firstElementChild?.tagName).toBe('SECTION')
  })
})

describe('Stack', () => {
  it('applies flex-col layout', () => {
    const { container } = render(<Stack gap={8}>x</Stack>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('flex')
    expect(el.className).toContain('flex-col')
  })

  it('applies gap from §G spacing scale', () => {
    const { container } = render(<Stack gap={16}>x</Stack>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toMatch(/gap/)
  })

  it('accepts align and justify props', () => {
    const { container } = render(<Stack gap={8} align="center" justify="between">x</Stack>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('items-center')
    expect(el.className).toContain('justify-between')
  })

  it('forwards ref', () => {
    const ref = createRef<HTMLDivElement>()
    render(<Stack gap={8} ref={ref}>x</Stack>)
    expect(ref.current).toBeTruthy()
  })
})

describe('Cluster', () => {
  it('applies flex-row and flex-wrap layout', () => {
    const { container } = render(<Cluster gap={8}>x</Cluster>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('flex')
    expect(el.className).toContain('flex-wrap')
  })

  it('applies gap from §G spacing scale', () => {
    const { container } = render(<Cluster gap={12}>x</Cluster>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toMatch(/gap/)
  })

  it('forwards ref', () => {
    const ref = createRef<HTMLDivElement>()
    render(<Cluster gap={8} ref={ref}>x</Cluster>)
    expect(ref.current).toBeTruthy()
  })
})

describe('Surface', () => {
  it('renders a div by default', () => {
    const { container } = render(<Surface elevation="raised">x</Surface>)
    expect(container.firstElementChild?.tagName).toBe('DIV')
  })

  it('elevation=surface applies shadow-1 class', () => {
    const { container } = render(<Surface elevation="surface">x</Surface>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('shadow-1')
  })

  it('elevation=raised applies shadow-2 class', () => {
    const { container } = render(<Surface elevation="raised">x</Surface>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('shadow-2')
  })

  it('elevation=modal applies shadow-3 class', () => {
    const { container } = render(<Surface elevation="modal">x</Surface>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('shadow-3')
  })

  it('elevation=toast applies shadow-4 class', () => {
    const { container } = render(<Surface elevation="toast">x</Surface>)
    const el = container.firstElementChild as HTMLElement
    expect(el.className).toContain('shadow-4')
  })

  it('forwards ref', () => {
    const ref = createRef<HTMLDivElement>()
    render(<Surface elevation="raised" ref={ref}>x</Surface>)
    expect(ref.current).toBeTruthy()
  })

  it('renders as a different element via as prop', () => {
    const { container } = render(<Surface elevation="raised" as="article">x</Surface>)
    expect(container.firstElementChild?.tagName).toBe('ARTICLE')
  })
})

describe('§G spacing scale type safety (runtime check)', () => {
  it('all valid gap values render without error', () => {
    for (const gap of VALID_GAPS) {
      expect(() => render(<Stack gap={gap}>x</Stack>)).not.toThrow()
    }
  })
})
