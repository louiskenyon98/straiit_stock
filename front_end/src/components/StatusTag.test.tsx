// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusTag } from './StatusTag'

describe('StatusTag', () => {
  it('uses the available treatment for available stock', () => {
    render(<StatusTag status="AVAILABLE" label="Available" />)
    expect(screen.getByText('Available')).toHaveClass('tag-accent')
  })

  it('renders nothing when the imported status is missing', () => {
    const { container } = render(<StatusTag status={null} label={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
