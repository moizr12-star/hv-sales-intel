export interface Practice {
  place_id: string
  name: string
  address: string | null
  city: string | null
  state: string | null
  phone: string | null
  website: string | null
  rating: number | null
  review_count: number
  category: string | null
  lat: number | null
  lng: number | null
  opening_hours: string | null
  status: string

  // Phase 2 (AI analysis) — optional, absent on unscored practices
  summary?: string | null
  pain_points?: string | null  // JSON string of string[]
  sales_angles?: string | null // JSON string of string[]
  lead_score?: number | null
  urgency_score?: number | null
  hiring_signal_score?: number | null

  // Phase 3 (Call Playbook)
  call_script?: string | null // JSON string of Script
  notes?: string | null

  // Attribution (last-touched)
  last_touched_by: string | null
  last_touched_by_name: string | null
  last_touched_at: string | null
}

export interface ScriptSection {
  title: string
  icon: string
  content: string
}

export interface Script {
  sections: ScriptSection[]
}

/** Parse a JSON string array field, returning [] on failure. */
export function parseJsonArray(value: string | null): string[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export interface User {
  id: string
  email: string
  name: string | null
  role: "admin" | "rep"
  created_at?: string
}
