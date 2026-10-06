import { render, screen } from '@testing-library/react'
import Home from '../app/page'

describe('Home', () => {
  it('renders heading', () => {
    render(<Home />)
    expect(screen.getByText('Demo App')).toBeInTheDocument()
  })
})
