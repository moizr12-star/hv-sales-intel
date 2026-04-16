"use client"

import { Phone, Search, Target, Shield, CheckCircle, Loader2, RefreshCw } from "lucide-react"
import type { ScriptSection } from "@/lib/types"

const ICON_MAP: Record<string, React.ElementType> = {
  phone: Phone,
  search: Search,
  target: Target,
  shield: Shield,
  check: CheckCircle,
}

interface ScriptViewProps {
  sections: ScriptSection[]
  isLoading: boolean
  onRegenerate: () => void
}

export default function ScriptView({ sections, isLoading, onRegenerate }: ScriptViewProps) {
  if (isLoading && sections.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Generating playbook...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {sections.map((section, i) => {
        const Icon = ICON_MAP[section.icon] ?? Phone
        return (
          <div key={i} className="space-y-2">
            <div className="flex items-center gap-2">
              <Icon className="w-4 h-4 text-teal-600" />
              <h3 className="font-serif font-semibold text-gray-900">{section.title}</h3>
            </div>
            <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line pl-6">
              {section.content}
            </div>
          </div>
        )
      })}

      <button
        onClick={onRegenerate}
        disabled={isLoading}
        className="inline-flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg border border-teal-600 text-teal-700 hover:bg-teal-50 disabled:opacity-50 transition"
      >
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <RefreshCw className="w-4 h-4" />
        )}
        {isLoading ? "Regenerating..." : "Regenerate Script"}
      </button>
    </div>
  )
}
