export interface Practice {
  place_id: string
  name: string
  address: string | null
  city: string | null
  state: string | null
  phone: string | null
  website: string | null
  rating: number | null
  review_count: number
  category: string | null
  lat: number | null
  lng: number | null
  opening_hours: string | null
  status: string
}
