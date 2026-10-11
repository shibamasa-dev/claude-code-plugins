'use client'

import { useState, useEffect } from 'react'

export default function Home() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    console.log('Page mounted')  // violates CLAUDE.md: uses console.log
  }, [])

  return (
    <main>
      <h1>Demo App</h1>
      <p>Count: {count}</p>
      <button onClick={() => setCount(c => c + 1)}>Increment</button>
    </main>
  )
}
