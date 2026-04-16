import { Phone, Globe, Star } from "lucide-react"
import type { Practice } from "@/lib/types"
import { cn } from "@/lib/utils"

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

interface PracticeCardProps {
  practice: Practice
  isSelected: boolean
  onSelect: (placeId: string) => void
}

export default function PracticeCard({ practice, isSelected, onSelect }: PracticeCardProps) {
  return (
    <button
      onClick={() => onSelect(practice.place_id)}
      className={cn(
        "w-full text-left p-4 rounded-xl transition-all",
        "hover:bg-ivory-200/60",
        isSelected ? "bg-teal-50 ring-1 ring-teal-600/30" : "bg-white/60"
      )}
    >
      <h3 className="font-serif font-semibold text-gray-900 text-base leading-tight">
        {practice.name}
      </h3>
      <p className="text-xs text-gray-500 mt-0.5">{practice.address}</p>

      <div className="flex items-center gap-3 mt-2">
        <StarRating rating={practice.rating} />
        {practice.review_count > 0 && (
          <span className="text-xs text-gray-400">({practice.review_count})</span>
        )}
      </div>

      {practice.category && (
        <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 font-medium capitalize">
          {practice.category.replace("_", " ")}
        </span>
      )}

      <div className="flex gap-2 mt-3">
        {practice.phone && (
          <a
            href={`tel:${practice.phone}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
          >
            <Phone className="w-3 h-3" /> Call
          </a>
        )}
        {practice.website && (
          <a
            href={practice.website}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition"
          >
            <Globe className="w-3 h-3" /> Website
          </a>
        )}
      </div>
    </button>
  )
}
