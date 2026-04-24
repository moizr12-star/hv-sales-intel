"use client"

import { useEffect, useRef } from "react"
import type { Practice } from "./types"
import { getPractice } from "./api"

const POLL_INTERVAL_MS = 5_000
const MAX_POLLS = 36 // 36 × 5s = 3 min

/**
 * While `practice.enrichment_status === 'pending'`, re-fetch the practice
 * every 5 seconds. Calls `onUpdate` whenever the server row differs.
 * Stops on status change or after MAX_POLLS iterations.
 */
export function useEnrichmentPoll(
  practice: Practice,
  onUpdate: (next: Practice) => void,
) {
  const pollsRef = useRef(0)

  useEffect(() => {
    if (practice.enrichment_status !== "pending") {
      pollsRef.current = 0
      return
    }

    let cancelled = false
    const handle = window.setInterval(async () => {
      if (pollsRef.current >= MAX_POLLS) {
        window.clearInterval(handle)
        return
      }
      pollsRef.current += 1
      try {
        const fresh = await getPractice(practice.place_id)
        if (cancelled) return
        if (fresh.enrichment_status !== "pending") {
          onUpdate(fresh)
          window.clearInterval(handle)
        } else {
          onUpdate(fresh)
        }
      } catch {
        // swallow — next tick will retry
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(handle)
    }
  }, [practice.place_id, practice.enrichment_status, onUpdate])
}
