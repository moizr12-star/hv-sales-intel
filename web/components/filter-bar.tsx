"use client"

interface FilterBarProps {
  category: string
  onCategoryChange: (cat: string) => void
  minRating: number
  onMinRatingChange: (r: number) => void
}

const CATEGORIES = [
  { value: "", label: "All categories" },
  { value: "dental", label: "Dental" },
  { value: "chiropractic", label: "Chiropractic" },
  { value: "urgent_care", label: "Urgent Care" },
  { value: "mental_health", label: "Mental Health" },
  { value: "primary_care", label: "Primary Care" },
  { value: "specialty", label: "Specialty" },
]

export default function FilterBar({
  category,
  onCategoryChange,
  minRating,
  onMinRatingChange,
}: FilterBarProps) {
  return (
    <div className="flex items-center gap-3 px-5 py-2 border-b border-gray-200/50">
      <select
        value={category}
        onChange={(e) => onCategoryChange(e.target.value)}
        className="text-sm rounded-lg border border-gray-200 bg-white/80 px-3 py-1.5
                   focus:outline-none focus:ring-2 focus:ring-teal-500/40"
      >
        {CATEGORIES.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-sm text-gray-600">
        Min rating
        <input
          type="range"
          min={0}
          max={5}
          step={0.5}
          value={minRating}
          onChange={(e) => onMinRatingChange(Number(e.target.value))}
          className="w-24 accent-teal-600"
        />
        <span className="text-xs font-medium w-6">{minRating || "Any"}</span>
      </label>
    </div>
  )
}
