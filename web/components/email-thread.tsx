"use client"

import { useState } from "react"
import { ArrowLeft, ArrowRight, AlertCircle, ChevronDown, ChevronUp, RefreshCw, Loader2 } from "lucide-react"
import type { EmailMessage } from "@/lib/types"
import { cn, timeAgo } from "@/lib/utils"

interface EmailThreadProps {
  messages: EmailMessage[]
  onPoll: () => Promise<void>
  onMarkReplied: () => Promise<void>
  isPolling: boolean
}

export default function EmailThread({
  messages,
  onPoll,
  onMarkReplied,
  isPolling,
}: EmailThreadProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Thread
        </h4>
        <div className="flex gap-1.5">
          <button
            onClick={onPoll}
            disabled={isPolling}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {isPolling ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
            Check replies
          </button>
          <button
            onClick={onMarkReplied}
            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Mark replied
          </button>
        </div>
      </div>

      {messages.length === 0 ? (
        <p className="text-xs text-gray-400">No messages yet.</p>
      ) : (
        <ul className="space-y-1">
          {messages.map((m) => {
            const isExpanded = expandedId === m.id
            const Icon = m.direction === "out" ? ArrowRight : ArrowLeft
            const color = m.error ? "text-rose-500" : m.direction === "out" ? "text-teal-600" : "text-gray-500"
            return (
              <li
                key={m.id}
                className={cn(
                  "rounded-lg border border-gray-200/60 bg-white/60",
                  m.error && "border-rose-200 bg-rose-50/60"
                )}
              >
                <button
                  onClick={() => setExpandedId(isExpanded ? null : m.id)}
                  className="w-full flex items-center gap-2 px-3 py-2 text-left"
                >
                  {m.error ? (
                    <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                  ) : (
                    <Icon className={cn("w-3.5 h-3.5 shrink-0", color)} />
                  )}
                  <span className="text-xs font-medium text-gray-700 truncate flex-1">
                    {m.subject || (m.error ? "Send failed" : "(no subject)")}
                  </span>
                  <span className="text-[11px] text-gray-400 shrink-0">
                    {timeAgo(m.sent_at)}
                  </span>
                  {isExpanded ? (
                    <ChevronUp className="w-3 h-3 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  )}
                </button>
                {isExpanded && (
                  <div className="px-3 pb-3 text-xs text-gray-700 whitespace-pre-line">
                    {m.error ? (
                      <span className="text-rose-700">{m.error}</span>
                    ) : (
                      m.body || "(no body)"
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
