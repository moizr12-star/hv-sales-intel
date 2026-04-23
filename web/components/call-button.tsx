"use client"

import { useState } from "react"
import { Phone } from "lucide-react"
import type { Practice } from "@/lib/types"
import type { CallLogResponse } from "@/lib/api"
import CallLogModal from "./call-log-modal"

interface CallButtonProps {
  practice: Practice
  label?: string
  className: string
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void
  onLogged?: (response: CallLogResponse) => void
}

export default function CallButton({
  practice,
  label = "Call",
  className,
  onClick,
  onLogged,
}: CallButtonProps) {
  const [open, setOpen] = useState(false)

  if (!practice.phone) return null

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          onClick?.(event)
          setOpen(true)
        }}
        className={className}
        title={`Log call + dial via RingCentral: ${practice.phone}`}
      >
        <Phone className="w-3 h-3" /> {label}
      </button>
      <CallLogModal
        practice={practice}
        open={open}
        onClose={() => setOpen(false)}
        onLogged={(response) => onLogged?.(response)}
      />
    </>
  )
}
