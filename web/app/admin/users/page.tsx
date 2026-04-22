"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { ArrowLeft, Trash2, Loader2 } from "lucide-react"
import { useAuth } from "@/lib/auth"

interface AdminUser {
  id: string
  email: string
  name: string | null
  role: "admin" | "rep"
  created_at: string
  practices_touched: number
}

export default function AdminUsersPage() {
  const { user, loading: authLoading } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "rep" })

  const API_URL = process.env.NEXT_PUBLIC_API_URL || ""

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_URL}/api/admin/users`, { credentials: "include" })
      if (!res.ok) throw new Error(`${res.status}`)
      const data = await res.json()
      setUsers(data.users)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [API_URL])

  useEffect(() => {
    if (user?.role === "admin") load()
  }, [user, load])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    setError(null)
    try {
      const res = await fetch(`${API_URL}/api/admin/users`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `HTTP ${res.status}`)
      }
      setForm({ email: "", name: "", password: "", role: "rep" })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this user?")) return
    const res = await fetch(`${API_URL}/api/admin/users/${id}`, {
      method: "DELETE",
      credentials: "include",
    })
    if (res.ok) load()
    else setError(`HTTP ${res.status}`)
  }

  if (authLoading) return <div className="p-10 text-gray-500">Loading...</div>

  if (user?.role !== "admin") {
    return (
      <div className="min-h-screen bg-cream p-10">
        <p className="text-rose-600 font-medium">Admin only</p>
        <Link href="/" className="text-sm text-teal-700 underline">Back to map</Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-cream">
      <header className="sticky top-0 z-20 h-14 flex items-center justify-between px-6 bg-white/70 backdrop-blur-md border-b border-gray-200/50">
        <Link href="/" className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeft className="w-4 h-4" /> Back to Map
        </Link>
        <span className="font-serif text-lg font-bold text-teal-700">Users</span>
        <span />
      </header>

      <main className="max-w-4xl mx-auto p-8 space-y-8">
        <section>
          <h2 className="font-serif text-xl font-bold mb-4">Create rep</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-3 bg-white/80 p-4 rounded-xl">
            <input
              placeholder="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              className="text-sm rounded-lg border border-gray-200 px-3 py-2"
            />
            <input
              placeholder="Name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              className="text-sm rounded-lg border border-gray-200 px-3 py-2"
            />
            <input
              placeholder="Initial password"
              type="text"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
              minLength={8}
              className="text-sm rounded-lg border border-gray-200 px-3 py-2"
            />
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="text-sm rounded-lg border border-gray-200 px-3 py-2"
            >
              <option value="rep">Rep</option>
              <option value="admin">Admin</option>
            </select>
            <button
              type="submit"
              disabled={creating}
              className="col-span-2 text-sm px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition inline-flex items-center justify-center gap-2"
            >
              {creating && <Loader2 className="w-4 h-4 animate-spin" />}
              {creating ? "Creating..." : "Create user"}
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
        </section>

        <section>
          <h2 className="font-serif text-xl font-bold mb-4">All users</h2>
          {loading ? (
            <p className="text-gray-500">Loading...</p>
          ) : (
            <table className="w-full bg-white/80 rounded-xl text-sm">
              <thead>
                <tr className="text-left text-gray-500 text-xs uppercase tracking-wide">
                  <th className="p-3">Email</th>
                  <th className="p-3">Name</th>
                  <th className="p-3">Role</th>
                  <th className="p-3">Touched</th>
                  <th className="p-3">Created</th>
                  <th className="p-3" />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-gray-200/50">
                    <td className="p-3">{u.email}</td>
                    <td className="p-3">{u.name ?? "—"}</td>
                    <td className="p-3 capitalize">{u.role}</td>
                    <td className="p-3">{u.practices_touched}</td>
                    <td className="p-3 text-gray-500">{u.created_at.slice(0, 10)}</td>
                    <td className="p-3 text-right">
                      {u.id !== user.id && (
                        <button
                          onClick={() => handleDelete(u.id)}
                          className="text-rose-600 hover:text-rose-800"
                          title="Delete user"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </div>
  )
}
