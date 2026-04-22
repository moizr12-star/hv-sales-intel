"use client"

const RINGCENTRAL_WEB_APP_URL =
  process.env.NEXT_PUBLIC_RINGCENTRAL_WEB_APP_URL || "https://app.ringcentral.com"

function normalizePhoneNumber(phone: string): string {
  const trimmed = phone.trim()
  const hasPlus = trimmed.startsWith("+")
  const digits = trimmed.replace(/\D/g, "")

  if (!digits) return ""
  if (hasPlus) return `+${digits}`
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`
  if (digits.length === 10) return `+1${digits}`
  return `+${digits}`
}

export function buildRingCentralCallUrls(phone: string) {
  const e164 = normalizePhoneNumber(phone)
  const encoded = encodeURIComponent(e164)

  return {
    normalized: e164,
    appUrl: `rcmobile://call?number=${encoded}`,
    webUrl: `${RINGCENTRAL_WEB_APP_URL}/r/call?number=${encoded}`,
    telUrl: `tel:${e164}`,
  }
}

export function openRingCentralCall(phone: string) {
  const urls = buildRingCentralCallUrls(phone)
  if (!urls.normalized) return

  const fallbackToWeb = window.setTimeout(() => {
    window.open(urls.webUrl, "_blank", "noopener,noreferrer")
  }, 900)

  const clearFallback = () => {
    window.clearTimeout(fallbackToWeb)
    window.removeEventListener("blur", clearFallback)
    document.removeEventListener("visibilitychange", handleVisibilityChange)
  }

  const handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      clearFallback()
    }
  }

  window.addEventListener("blur", clearFallback, { once: true })
  document.addEventListener("visibilitychange", handleVisibilityChange)
  window.location.assign(urls.appUrl)
}
