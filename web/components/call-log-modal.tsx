"use client"

import { useState } from "react"
import { Loader2, Phone, X } from "lucide-react"
import type { Practice } from "@/lib/types"
import { logCall, type CallLogResponse } from "@/lib/api"
import { openRingCentralCall } from "@/lib/ringcentral"

interface CallLogModalProps {
  practice: Practice
  open: boolean
  onClose: () => void
  onLogged: (response: CallLogResponse) => void
}

export default function CallLogModal({
  practice,
  open,
  onClose,
  onLogged,
}: CallLogModalProps) {
  const [note, setNote] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  async function handleSaveAndCall() {
    setSubmitting(true)
    setError(null)
    try {
      const response = await logCall(practice.place_id, note)
      onLogged(response)
      setNote("")
      onClose()
      if (practice.phone) openRingCentralCall(practice.phone)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to log call")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-xl p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-serif text-base font-bold text-gray-900">
            Log call — {practice.name}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What happened? (we'll polish this for Salesforce)"
          className="w-full h-32 text-sm p-3 rounded-lg border border-gray-200 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-teal-500/40"
          disabled={submitting}
          autoFocus
        />
        {error && <p className="text-xs text-rose-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-xs px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveAndCall}
            disabled={submitting}
            className="inline-flex items-center gap-1 text-xs px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50"
          >
            {submitting ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Phone className="w-3 h-3" />
            )}
            {submitting ? "Saving..." : "Save & Call"}
          </button>
        </div>
      </div>
    </div>
  )
}
