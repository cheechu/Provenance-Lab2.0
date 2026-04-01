'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

type Mode = 'therapeutic' | 'agricultural'

// ── Icons ──────────────────────────────────────────────────────────────────

function IconPlus() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

function IconList() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2 3.5h10M2 7h10M2 10.5h6.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

function IconBars() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2 12V7.5M5 12V4M8 12V8.5M11 12V2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

function IconTrophy() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M4.5 1.5h5v5a2.5 2.5 0 0 1-5 0v-5ZM2 2h2.5M9.5 2H12M2 2c0 2.2.9 3.8 2.5 4.5M12 2c0 2.2-.9 3.8-2.5 4.5M7 9v2.5M4.5 12.5h5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconGear() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="2" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M7 1v1.5M7 11.5V13M13 7h-1.5M2.5 7H1M11.24 2.76l-1.06 1.06M3.82 10.18l-1.06 1.06M11.24 11.24l-1.06-1.06M3.82 3.82L2.76 2.76"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  )
}

// ── Nav config ─────────────────────────────────────────────────────────────

const NAV_ITEMS = [
  { href: '/runs', label: 'Runs', Icon: IconList },
  { href: '/benchmarks', label: 'Benchmarks', Icon: IconBars },
  { href: '/leaderboard', label: 'Leaderboard', Icon: IconTrophy },
] as const

// ── Shared nav-link class helpers ───────────────────────────────────────────
// border-l-2 is always present (transparent when inactive) so text never shifts.
// pl-[10px] = 12px (px-3) - 2px (border) to keep text visually aligned.

function navClass(active: boolean) {
  const base =
    'flex items-center gap-2.5 pl-[10px] pr-3 py-[7px] rounded-md text-[13px] transition-colors duration-100 border-l-2'
  return active
    ? `${base} border-teal-500 bg-slate-100 text-slate-900 font-medium`
    : `${base} border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50`
}

// ── Component ──────────────────────────────────────────────────────────────

export function Sidebar() {
  const pathname = usePathname()
  const [mode, setMode] = useState<Mode>('therapeutic')

  return (
    <aside className="fixed left-0 top-0 h-screen w-[240px] border-r border-slate-200 bg-white flex flex-col z-20 select-none">

      {/* Wordmark ──────────────────────────────────────────────────────── */}
      <div className="px-4 py-4 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          {/* Badge */}
          <div className="w-7 h-7 rounded-[5px] bg-teal-600 flex items-center justify-center flex-shrink-0">
            <span className="font-mono text-[10px] font-bold text-white tracking-tighter">CA</span>
          </div>
          {/* Text */}
          <div className="flex flex-col leading-none">
            <span className="text-[13px] font-semibold text-slate-900 tracking-tight">CasAI</span>
            <span className="text-[10px] font-mono text-slate-400 mt-0.5 tracking-wide">Provenance Lab</span>
          </div>
        </div>
      </div>

      {/* Primary nav ───────────────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-3 flex flex-col gap-0.5 overflow-y-auto">

        {/* New Run — styled as an action, not a plain link */}
        <Link
          href="/runs"
          className="flex items-center gap-2.5 px-3 py-[7px] mb-3 rounded-md text-[13px] font-medium
                     text-teal-700 bg-teal-50 border border-teal-200/70
                     hover:bg-teal-100 hover:border-teal-300/70
                     transition-colors duration-100"
        >
          <IconPlus />
          <span>New Run</span>
        </Link>

        {NAV_ITEMS.map(({ href, label, Icon }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link key={href} href={href} className={navClass(active)}>
              <Icon />
              <span>{label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Bottom section ────────────────────────────────────────────────── */}
      <div className="px-3 pb-4 pt-3 border-t border-slate-100 flex flex-col gap-3">

        {/* Mode toggle — segmented control */}
        <div>
          <p className="text-[10px] font-mono text-slate-400 uppercase tracking-widest px-1 mb-1.5">
            Mode
          </p>
          <div className="flex bg-slate-100 rounded-[6px] p-[3px] gap-[3px]">
            <button
              onClick={() => setMode('therapeutic')}
              className={`flex-1 py-1.5 rounded-[4px] text-[11px] font-medium transition-all duration-150 ${
                mode === 'therapeutic'
                  ? 'bg-white text-slate-900 shadow-sm shadow-slate-200'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Therapeutic
            </button>
            <button
              onClick={() => setMode('agricultural')}
              className={`flex-1 py-1.5 rounded-[4px] text-[11px] font-medium transition-all duration-150 ${
                mode === 'agricultural'
                  ? 'bg-white text-slate-900 shadow-sm shadow-slate-200'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Agricultural
            </button>
          </div>
        </div>

        {/* Settings */}
        <Link href="/settings" className={navClass(pathname === '/settings')}>
          <IconGear />
          <span>Settings</span>
        </Link>
      </div>
    </aside>
  )
}
