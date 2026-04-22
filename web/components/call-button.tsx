"use client"

import { Phone } from "lucide-react"
import { buildRingCentralCallUrls, openRingCentralCall } from "@/lib/ringcentral"

interface CallButtonProps {
  phone: string
  label?: string
  className: string
  onClick?: (event: React.MouseEvent<HTMLAnchorElement>) => void
}

export default function CallButton({
  phone,
  label = "Call",
  className,
  onClick,
}: CallButtonProps) {
  const urls = buildRingCentralCallUrls(phone)

  return (
    <a
      href={urls.webUrl}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(event) => {
        onClick?.(event)
        event.preventDefault()
        openRingCentralCall(phone)
      }}
      className={className}
      title={`Call via RingCentral: ${phone}`}
    >
      <Phone className="w-3 h-3" /> {label}
    </a>
  )
}
