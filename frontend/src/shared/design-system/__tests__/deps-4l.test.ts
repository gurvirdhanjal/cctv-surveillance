import { describe, it, expect } from 'vitest'

describe('Phase 4L package smoke tests', () => {
  it('sonner Toaster is importable', async () => {
    const { Toaster } = await import('sonner')
    expect(Toaster).toBeTruthy()
  })

  it('@dnd-kit/core DndContext is importable', async () => {
    const { DndContext } = await import('@dnd-kit/core')
    expect(DndContext).toBeTruthy()
  })

  it('@dnd-kit/sortable SortableContext is importable', async () => {
    const { SortableContext } = await import('@dnd-kit/sortable')
    expect(SortableContext).toBeTruthy()
  })

  it('react-resizable-panels Panel is importable', async () => {
    const { Panel } = await import('react-resizable-panels')
    expect(Panel).toBeTruthy()
  })

  it('react-virtuoso Virtuoso is importable', async () => {
    const { Virtuoso } = await import('react-virtuoso')
    expect(Virtuoso).toBeTruthy()
  })

  it('echarts-for-react is importable', async () => {
    const mod = await import('echarts-for-react')
    expect(mod.default ?? mod).toBeTruthy()
  })

  it('cmdk Command is importable (already installed)', async () => {
    const { Command } = await import('cmdk')
    expect(Command).toBeTruthy()
  })
})
