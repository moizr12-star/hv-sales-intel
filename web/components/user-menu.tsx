"use client"

import { useState } from "react"
import Link from "next/link"
import { LogOut, UserCog, KeyRound } from "lucide-react"
import { useAuth } from "@/lib/auth"
import ChangePasswordModal from "./change-password-modal"

export default function UserMenu() {
  const { user, loading, signOut } = useAuth()
  const [pwOpen, setPwOpen] = useState(false)

  if (loading || !user) return null

  return (
    <div className="flex items-center gap-2">
      {user.role === "admin" && (
        <Link
          href="/admin/users"
          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg
                     border border-gray-300 text-gray-700 hover:bg-gray-50 transition"
        >
          <UserCog className="w-3.5 h-3.5" /> Users
        </Link>
      )}
      <button
        onClick={() => setPwOpen(true)}
        title="Change password"
        className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg
                   border border-gray-300 text-gray-700 hover:bg-gray-50 transition"
      >
        <KeyRound className="w-3.5 h-3.5" /> Password
      </button>
      <div className="flex items-center gap-2 text-sm">
        <div className="w-7 h-7 rounded-full bg-teal-600 text-white grid place-items-center text-xs font-semibold">
          {(user.name?.[0] ?? user.email[0]).toUpperCase()}
        </div>
        <span className="text-gray-700 max-w-[120px] truncate">
          {user.name ?? user.email}
        </span>
      </div>
      <button
        onClick={signOut}
        title="Sign out"
        className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition"
      >
        <LogOut className="w-4 h-4" />
      </button>

      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
    </div>
  )
}
