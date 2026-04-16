"use client"

import SearchBar from "./search-bar"

interface TopBarProps {
  onSearch: (query: string) => void
  isLoading: boolean
}

export default function TopBar({ onSearch, isLoading }: TopBarProps) {
  return (
    <header className="fixed top-0 left-0 right-0 z-20 h-14 flex items-center justify-between px-6 bg-white/70 backdrop-blur-md border-b border-gray-200/50">
      <div className="flex items-center gap-2">
        <span className="font-serif text-lg font-bold text-teal-700 tracking-tight">
          Health&amp;Virtuals
        </span>
        <span className="text-xs text-gray-400 font-medium">Sales Intel</span>
      </div>
      <SearchBar onSearch={onSearch} isLoading={isLoading} />
    </header>
  )
}
