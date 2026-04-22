import { Globe, Star } from "lucide-react"
import type { Practice } from "@/lib/types"
import { parseJsonArray } from "@/lib/types"
import { cn } from "@/lib/utils"
import ScoreBar from "./score-bar"
import CallButton from "./call-button"

function StarRating({ rating }: { rating: number | null }) {
  if (!rating) return null
  const full = Math.floor(rating)
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          className={cn(
            "w-3.5 h-3.5",
            i < full ? "fill-amber-400 text-amber-400" : "text-gray-300"
          )}
        />
      ))}
      <span className="ml-1 text-sm font-medium text-gray-700">{rating}</span>
    </span>
  )
}

export default function PracticeInfo({ practice }: { practice: Practice }) {
  const painPoints = parseJsonArray(practice.pain_points ?? null)
  const salesAngles = parseJsonArray(practice.sales_angles ?? null)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-serif text-xl font-bold text-gray-900">{practice.name}</h2>
        <p className="text-sm text-gray-500 mt-1">{practice.address}</p>
      </div>

      <div className="flex items-center gap-3">
        <StarRating rating={practice.rating} />
        {practice.review_count > 0 && (
          <span className="text-xs text-gray-400">({practice.review_count})</span>
        )}
      </div>

      {practice.category && (
        <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 font-medium capitalize">
          {practice.category.replace("_", " ")}
        </span>
      )}

      <div className="flex gap-2">
        {practice.phone && (
          <CallButton
            phone={practice.phone}
            label={practice.phone}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
          />
        )}
        {practice.website && (
          <a
            href={practice.website}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition"
          >
            <Globe className="w-3 h-3" /> Website
          </a>
        )}
      </div>

      {practice.lead_score != null && (
        <div className="pt-3 border-t border-gray-200/50 space-y-3">
          {practice.summary && (
            <p className="text-xs text-gray-600 leading-relaxed">{practice.summary}</p>
          )}

          {painPoints.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-700 mb-1">Pain Points</h4>
              <ul className="space-y-0.5">
                {painPoints.map((p, i) => (
                  <li key={i} className="text-xs text-gray-500 flex gap-1.5">
                    <span className="text-rose-400 shrink-0">&bull;</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {salesAngles.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-gray-700 mb-1">Sales Angles</h4>
              <ul className="space-y-0.5">
                {salesAngles.map((a, i) => (
                  <li key={i} className="text-xs text-gray-500 flex gap-1.5">
                    <span className="text-teal-500 shrink-0">&rarr;</span>
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="space-y-1.5">
            <ScoreBar label="Lead" value={practice.lead_score!} />
            <ScoreBar label="Urgency" value={practice.urgency_score!} />
            <ScoreBar label="Hiring" value={practice.hiring_signal_score!} />
          </div>
        </div>
      )}
    </div>
  )
}
