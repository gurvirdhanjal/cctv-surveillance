import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './Tabs'

function TabsFixture() {
  return (
    <Tabs defaultValue="tab1">
      <TabsList>
        <TabsTrigger value="tab1">Overview</TabsTrigger>
        <TabsTrigger value="tab2">Settings</TabsTrigger>
      </TabsList>
      <TabsContent value="tab1">Overview content</TabsContent>
      <TabsContent value="tab2">Settings content</TabsContent>
    </Tabs>
  )
}

describe('Tabs', () => {
  it('renders tabs with default active tab', () => {
    render(<TabsFixture />)
    expect(screen.getByText('Overview content')).toBeInTheDocument()
  })

  it('switches tabs on click', async () => {
    render(<TabsFixture />)
    await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    expect(screen.getByText('Settings content')).toBeInTheDocument()
  })

  it('tab list has correct ARIA role', () => {
    render(<TabsFixture />)
    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })
})
