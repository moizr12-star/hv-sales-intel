import { cn } from "@/lib/utils"

const STATUS_COLORS: Record<string, string> = {
  NEW: "bg-gray-100 text-gray-600",
  RESEARCHED: "bg-blue-100 text-blue-700",
  "SCRIPT READY": "bg-blue-100 text-blue-700",
  CONTACTED: "bg-amber-100 text-amber-700",
  "FOLLOW UP": "bg-amber-100 text-amber-700",
  "MEETING SET": "bg-teal-100 text-teal-700",
  PROPOSAL: "bg-teal-100 text-teal-700",
  "CLOSED WON": "bg-green-100 text-green-700",
  "CLOSED LOST": "bg-rose-100 text-rose-700",
}

export default function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "bg-gray-100 text-gray-600"
  return (
    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide", color)}>
      {status}
    </span>
  )
}

export const ALL_STATUSES = [
  "NEW",
  "RESEARCHED",
  "SCRIPT READY",
  "CONTACTED",
  "FOLLOW UP",
  "MEETING SET",
  "PROPOSAL",
  "CLOSED WON",
  "CLOSED LOST",
]
