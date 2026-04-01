import { Sidebar } from './Sidebar'

interface AppLayoutProps {
  children: React.ReactNode
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar />
      <main className="ml-[240px] flex-1 overflow-auto min-h-screen">
        <div className="px-8 py-7 min-h-full">
          {children}
        </div>
      </main>
    </div>
  )
}
