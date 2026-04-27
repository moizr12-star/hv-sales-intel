import { Globe, Star } from "lucide-react"
import type { Practice } from "@/lib/types"
import type { CallLogResponse } from "@/lib/api"
import { parseJsonArray, parseIcpBreakdown } from "@/lib/types"
import { cn } from "@/lib/utils"
import CallButton from "./call-button"
import OwnerMiniCard from "./owner-mini-card"

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

export default function PracticeInfo({
  practice,
  onCallLogged,
}: {
  practice: Practice
  onCallLogged?: (response: CallLogResponse) => void
}) {
  const painPoints = parseJsonArray(practice.pain_points ?? null)
  const salesAngles = parseJsonArray(practice.sales_angles ?? null)
  const icpBreakdown = parseIcpBreakdown(practice.icp_breakdown ?? null)

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
            practice={practice}
            label={practice.phone}
            onLogged={onCallLogged}
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

      {(practice.website_doctor_name || practice.website_doctor_phone) && (
        <div>
          <h4 className="text-xs font-semibold text-gray-700 mb-1">From website</h4>
          <div className="space-y-0.5">
            {practice.website_doctor_name && (
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Doctor</span>
                <span className="text-gray-900">{practice.website_doctor_name}</span>
              </div>
            )}
            {practice.website_doctor_phone && (
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Direct line</span>
                <a
                  href={`tel:${practice.website_doctor_phone.replace(/\D/g, "")}`}
                  className="text-teal-700 hover:underline"
                >
                  {practice.website_doctor_phone}
                </a>
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        <h4 className="text-xs font-semibold text-gray-700 mb-1">Owner</h4>
        {practice.enrichment_status === "pending" ? (
          <p className="text-xs text-gray-400">Enriching owner info…</p>
        ) : practice.owner_name ||
          practice.owner_email ||
          practice.owner_phone ? (
          <OwnerMiniCard practice={practice} />
        ) : (
          <p className="text-xs text-gray-400">
            {practice.enrichment_status === "failed"
              ? "No owner found."
              : "No owner info yet — enrich from the map."}
          </p>
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

          <div>
            <h4 className="text-xs font-semibold text-gray-700 mb-1">
              ICP score breakdown ({practice.lead_score}/100)
            </h4>
            {icpBreakdown.length > 0 ? (
              <ul className="space-y-1">
                {icpBreakdown.map((row, i) => (
                  <li key={i} className="text-[11px] text-gray-600 flex items-start gap-2">
                    <span className="font-mono text-gray-400 shrink-0 w-12 tabular-nums">
                      {row.score}/{row.max}
                    </span>
                    <span className="font-medium text-gray-700 shrink-0 w-28">
                      {row.label}
                    </span>
                    <span className="text-gray-500">{row.reason}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-gray-400 italic">
                Legacy score — re-analyze to populate the ICP breakdown.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
