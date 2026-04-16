"use client"

import { useState, useMemo, useCallback } from "react"
import dynamic from "next/dynamic"
import type { Practice } from "@/lib/types"
import { mockPractices } from "@/lib/mock-data"
import TopBar from "@/components/top-bar"
import PracticeCard from "@/components/practice-card"
import FilterBar from "@/components/filter-bar"
import { searchPractices, analyzePractice } from "@/lib/api"

const MapView = dynamic(() => import("@/components/map-view"), { ssr: false })

export default function Page() {
  const [practices, setPractices] = useState<Practice[]>(mockPractices)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [cityLabel, setCityLabel] = useState("")
  const [category, setCategory] = useState("")
  const [minRating, setMinRating] = useState(0)
  const [statusFilter, setStatusFilter] = useState("ACTIVE")
  const [analyzingIds, setAnalyzingIds] = useState<Set<string>>(new Set())
  const [scoreProgress, setScoreProgress] = useState<string | null>(null)

  const handleSearch = useCallback(async (query: string) => {
    setIsLoading(true)
    try {
      const results = await searchPractices(query)
      setPractices(results)
      setCityLabel(query)
      setSelectedId(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const handleAnalyze = useCallback(async (placeId: string) => {
    setAnalyzingIds((prev) => new Set(prev).add(placeId))
    try {
      const updated = await analyzePractice(placeId)
      setPractices((prev) =>
        prev.map((p) => (p.place_id === placeId ? { ...p, ...updated } : p))
      )
    } finally {
      setAnalyzingIds((prev) => {
        const next = new Set(prev)
        next.delete(placeId)
        return next
      })
    }
  }, [])

  const handleScoreAll = useCallback(async () => {
    const unscored = practices.filter((p) => p.lead_score == null)
    if (unscored.length === 0) return

    for (let i = 0; i < unscored.length; i++) {
      setScoreProgress(`Scoring ${i + 1}/${unscored.length}...`)
      const placeId = unscored[i].place_id
      setAnalyzingIds((prev) => new Set(prev).add(placeId))
      try {
        const updated = await analyzePractice(placeId)
        setPractices((prev) =>
          prev.map((p) => (p.place_id === placeId ? { ...p, ...updated } : p))
        )
      } finally {
        setAnalyzingIds((prev) => {
          const next = new Set(prev)
          next.delete(placeId)
          return next
        })
      }
    }
    setScoreProgress(null)
  }, [practices])

  const filtered = useMemo(() => {
    const list = practices.filter((p) => {
      if (category && p.category !== category) return false
      if (minRating && (p.rating ?? 0) < minRating) return false
      if (statusFilter === "ACTIVE" && p.status === "CLOSED LOST") return false
      if (statusFilter && statusFilter !== "ACTIVE" && p.status !== statusFilter) return false
      return true
    })
    return list.sort((a, b) => {
      const aScore = a.lead_score ?? -1
      const bScore = b.lead_score ?? -1
      return bScore - aScore
    })
  }, [practices, category, minRating, statusFilter])

  return (
    <div className="h-screen w-screen overflow-hidden">
      <TopBar
        onSearch={handleSearch}
        isLoading={isLoading}
        onScoreAll={handleScoreAll}
        scoreProgress={scoreProgress}
      />

      <main className="relative w-full h-full pt-14">
        {/* Sidebar */}
        <div className="absolute top-2 left-4 bottom-4 w-[390px] z-10 glass-panel rounded-2xl flex flex-col overflow-hidden">
          <div className="px-5 pt-5 pb-3 border-b border-gray-200/50">
            <h2 className="font-serif text-lg font-semibold text-gray-900">
              {cityLabel || "All practices"}
            </h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {filtered.length} practice{filtered.length !== 1 ? "s" : ""}
            </p>
          </div>
          <FilterBar
            category={category}
            onCategoryChange={setCategory}
            minRating={minRating}
            onMinRatingChange={setMinRating}
            status={statusFilter}
            onStatusChange={setStatusFilter}
          />
          <div className="flex-1 overflow-y-auto sidebar-scroll p-3 space-y-2">
            {filtered.length === 0 ? (
              <p className="text-center text-gray-400 py-10 text-sm">
                No practices found. Try a different search.
              </p>
            ) : (
              filtered.map((p) => (
                <PracticeCard
                  key={p.place_id}
                  practice={p}
                  isSelected={selectedId === p.place_id}
                  onSelect={setSelectedId}
                  onAnalyze={handleAnalyze}
                  isAnalyzing={analyzingIds.has(p.place_id)}
                />
              ))
            )}
          </div>
        </div>

        {/* Map */}
        <MapView
          practices={filtered}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </main>
    </div>
  )
}
