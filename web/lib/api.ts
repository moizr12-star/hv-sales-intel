import type { Practice } from "./types"
import { mockPractices } from "./mock-data"

const API_URL = process.env.NEXT_PUBLIC_API_URL || ""

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_URL) throw new Error("NO_API")
  const res = await fetch(`${API_URL}${path}`, init)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}

export async function searchPractices(query: string): Promise<Practice[]> {
  try {
    const data = await apiFetch<{ practices: Practice[] }>("/api/practices/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    })
    return data.practices
  } catch {
    const q = query.toLowerCase()
    const tokens = q.split(/\s+/)
    const matches = mockPractices.filter((p) => {
      const hay = `${p.name} ${p.category} ${p.city}`.toLowerCase()
      return tokens.some((t) => hay.includes(t))
    })
    return matches.length > 0 ? matches : mockPractices
  }
}

export async function listPractices(params?: {
  city?: string
  category?: string
  min_rating?: number
}): Promise<Practice[]> {
  try {
    const qs = new URLSearchParams()
    if (params?.city) qs.set("city", params.city)
    if (params?.category) qs.set("category", params.category)
    if (params?.min_rating) qs.set("min_rating", String(params.min_rating))
    const data = await apiFetch<{ practices: Practice[] }>(`/api/practices?${qs}`)
    return data.practices
  } catch {
    return mockPractices
  }
}
