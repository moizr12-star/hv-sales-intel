"use client"

import { useEffect, useRef } from "react"
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import type { Practice } from "@/lib/types"

function createPinIcon(rating: number | null): L.DivIcon {
  const label = rating ? rating.toFixed(1) : "\u2014"
  return L.divIcon({
    className: "",
    iconSize: [32, 42],
    iconAnchor: [16, 42],
    popupAnchor: [0, -42],
    html: `
      <svg width="32" height="42" viewBox="0 0 32 42" xmlns="http://www.w3.org/2000/svg">
        <path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 26 16 26s16-14 16-26C32 7.16 24.84 0 16 0z"
              fill="#0d9488" stroke="#fff" stroke-width="1.5"/>
        <text x="16" y="18" text-anchor="middle" fill="white"
              font-family="system-ui" font-size="10" font-weight="600">${label}</text>
      </svg>
    `,
  })
}

function FitBounds({ practices }: { practices: Practice[] }) {
  const map = useMap()
  useEffect(() => {
    const pts = practices
      .filter((p) => p.lat != null && p.lng != null)
      .map((p) => [p.lat!, p.lng!] as [number, number])
    if (pts.length > 0) {
      map.fitBounds(pts, { padding: [40, 40], maxZoom: 13 })
    }
  }, [practices, map])
  return null
}

interface MapViewProps {
  practices: Practice[]
  selectedId: string | null
  onSelect: (placeId: string) => void
}

export default function MapView({ practices, selectedId, onSelect }: MapViewProps) {
  const markerRefs = useRef<Record<string, L.Marker>>({})

  useEffect(() => {
    if (selectedId && markerRefs.current[selectedId]) {
      const marker = markerRefs.current[selectedId]
      marker.openPopup()
    }
  }, [selectedId])

  return (
    <MapContainer
      center={[29.76, -95.37]}
      zoom={10}
      className="w-full h-full z-0"
      zoomControl={false}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds practices={practices} />
      {practices
        .filter((p) => p.lat != null && p.lng != null)
        .map((p) => (
          <Marker
            key={p.place_id}
            position={[p.lat!, p.lng!]}
            icon={createPinIcon(p.rating)}
            ref={(ref) => {
              if (ref) markerRefs.current[p.place_id] = ref
            }}
            eventHandlers={{
              click: () => onSelect(p.place_id),
            }}
          >
            <Popup>
              <strong className="font-serif">{p.name}</strong>
              <br />
              {p.address}
            </Popup>
          </Marker>
        ))}
    </MapContainer>
  )
}
