"use client"

import { useCallback, useMemo } from "react"
import { useRouter, useSearchParams, usePathname } from "next/navigation"

export interface FilterState {
  q: string
  search: string
  cat: string
  rating: number
  minIcp: number
  tags: string[]
  enriched: "" | "yes" | "no"
  owner: string
  sel: string
}

export const EMPTY_FILTERS: FilterState = {
  q: "",
  search: "",
  cat: "",
  rating: 0,
  minIcp: 0,
  tags: [],
  enriched: "",
  owner: "",
  sel: "",
}

export function useUrlState(): [FilterState, (next: Partial<FilterState>) => void] {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()

  const state = useMemo<FilterState>(
    () => ({
      q: params.get("q") ?? "",
      search: params.get("search") ?? "",
      cat: params.get("cat") ?? "",
      rating: Number(params.get("rating") ?? 0),
      minIcp: Number(params.get("minIcp") ?? 0),
      tags: (params.get("tags") ?? "").split(",").filter(Boolean),
      enriched: (params.get("enriched") as "" | "yes" | "no") ?? "",
      owner: params.get("owner") ?? "",
      sel: params.get("sel") ?? "",
    }),
    [params],
  )

  const update = useCallback(
    (next: Partial<FilterState>) => {
      const merged = { ...state, ...next }
      const sp = new URLSearchParams()
      if (merged.q) sp.set("q", merged.q)
      if (merged.search) sp.set("search", merged.search)
      if (merged.cat) sp.set("cat", merged.cat)
      if (merged.rating) sp.set("rating", String(merged.rating))
      if (merged.minIcp) sp.set("minIcp", String(merged.minIcp))
      if (merged.tags.length > 0) sp.set("tags", merged.tags.join(","))
      if (merged.enriched) sp.set("enriched", merged.enriched)
      if (merged.owner) sp.set("owner", merged.owner)
      if (merged.sel) sp.set("sel", merged.sel)
      const qs = sp.toString()
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false })
    },
    [state, pathname, router],
  )

  return [state, update]
}
