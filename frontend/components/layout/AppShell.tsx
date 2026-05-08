'use client'

import { ReactNode } from 'react'
import Navbar from '@/components/Navbar'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-6 md:ml-48 md:px-6 lg:px-8">
        {children}
      </main>
    </div>
  )
}
