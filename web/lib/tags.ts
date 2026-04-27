export const ALL_TAGS = [
  "RESEARCHED",
  "SCRIPT_READY",
  "ENRICHED",
  "CONTACTED",
  "REPLIED",
  "MEETING_SET",
  "CLOSED_WON",
  "CLOSED_LOST",
] as const

export type Tag = (typeof ALL_TAGS)[number]

export const TAG_LABELS: Record<Tag, string> = {
  RESEARCHED: "Researched",
  SCRIPT_READY: "Script Ready",
  ENRICHED: "Enriched",
  CONTACTED: "Contacted",
  REPLIED: "Replied",
  MEETING_SET: "Meeting Set",
  CLOSED_WON: "Closed Won",
  CLOSED_LOST: "Closed Lost",
}

export const TAG_COLORS: Record<Tag, string> = {
  RESEARCHED: "bg-blue-100 text-blue-700",
  SCRIPT_READY: "bg-blue-100 text-blue-700",
  ENRICHED: "bg-purple-100 text-purple-700",
  CONTACTED: "bg-amber-100 text-amber-700",
  REPLIED: "bg-amber-100 text-amber-700",
  MEETING_SET: "bg-teal-100 text-teal-700",
  CLOSED_WON: "bg-green-100 text-green-700",
  CLOSED_LOST: "bg-rose-100 text-rose-700",
}
