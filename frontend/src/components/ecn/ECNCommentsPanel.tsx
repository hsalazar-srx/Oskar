import { useState, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import axiosInstance from "@/api/axios"
import { useAuthStore } from "@/store/auth"

interface Comment {
  id: string
  ecn_id: string
  author_username: string
  body: string
  created_at: string
  updated_at: string | null
}

async function fetchComments(ecnId: string): Promise<Comment[]> {
  const { data } = await axiosInstance.get(`/api/v1/ecn/${ecnId}/comments`)
  return data
}

async function postComment(ecnId: string, body: string): Promise<Comment> {
  const { data } = await axiosInstance.post(`/api/v1/ecn/${ecnId}/comments`, { body })
  return data
}

async function deleteComment(ecnId: string, commentId: string): Promise<void> {
  await axiosInstance.delete(`/api/v1/ecn/${ecnId}/comments/${commentId}`)
}

function initials(username: string) {
  return username.slice(0, 2).toUpperCase()
}

function relativeTime(iso: string) {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(ms / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" })
}

// ── ECNCommentsPanel ──────────────────────────────────────────────────────────

interface Props {
  ecnId: string
}

export default function ECNCommentsPanel({ ecnId }: Props) {
  const qc = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [draft, setDraft] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: comments = [], isLoading } = useQuery({
    queryKey: ["ecn-comments", ecnId],
    queryFn: () => fetchComments(ecnId),
    staleTime: 30_000,
  })

  const addMutation = useMutation({
    mutationFn: (body: string) => postComment(ecnId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ecn-comments", ecnId] })
      setDraft("")
      // Scroll to bottom after paint
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 100)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (commentId: string) => deleteComment(ecnId, commentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ecn-comments", ecnId] }),
  })

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && draft.trim()) {
      e.preventDefault()
      addMutation.mutate(draft.trim())
    }
  }

  const isUserDC = user?.groups?.includes("OSKAR-DC") ?? false

  return (
    <div className="rounded-xl border border-[#e8ecf0] bg-white shadow-[var(--shadow-sm)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-[#f1f5f9] bg-[#f8fafc]">
        <h2 className="text-sm font-semibold text-[#0f172a]">
          Notes &amp; Comments
          {comments.length > 0 && (
            <span className="ml-2 text-[11px] font-normal text-[#94a3b8]">{comments.length}</span>
          )}
        </h2>
      </div>

      <div className="p-5 space-y-4">
        {/* Comment thread */}
        {isLoading && (
          <div className="flex justify-center py-4">
            <div className="w-4 h-4 border-2 border-[#0066cc]/20 border-t-[#0066cc] rounded-full animate-spin" />
          </div>
        )}

        {!isLoading && comments.length === 0 && (
          <div className="py-6 flex flex-col items-center gap-1.5">
            <svg className="w-6 h-6 text-[#cbd5e1]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z"/>
            </svg>
            <p className="text-sm text-[#94a3b8]">No comments yet. Be the first to add a note.</p>
          </div>
        )}

        {comments.length > 0 && (
          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {comments.map((c) => {
              const isOwn = c.author_username === user?.username
              const canDelete = isOwn || isUserDC
              return (
                <div key={c.id} className="flex gap-3 group">
                  {/* Avatar */}
                  <div className="w-7 h-7 rounded-full bg-[#eff6ff] border border-[#dbeafe] flex items-center justify-center shrink-0 mt-0.5">
                    <span className="text-[10px] font-bold text-[#0066cc]">{initials(c.author_username)}</span>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="text-xs font-semibold text-[#0f172a]">{c.author_username}</span>
                      <span className="text-[10px] text-[#94a3b8]">{relativeTime(c.created_at)}</span>
                      {c.updated_at && (
                        <span className="text-[10px] text-[#cbd5e1]">(edited)</span>
                      )}
                    </div>
                    <p className="mt-0.5 text-sm text-[#475569] whitespace-pre-wrap break-words">{c.body}</p>
                  </div>

                  {/* Delete button — appears on hover */}
                  {canDelete && (
                    <button
                      className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5 text-[#cbd5e1] hover:text-red-400"
                      title="Delete comment"
                      onClick={() => {
                        if (window.confirm("Delete this comment?")) {
                          deleteMutation.mutate(c.id)
                        }
                      }}
                      disabled={deleteMutation.isPending}
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/>
                      </svg>
                    </button>
                  )}
                </div>
              )
            })}
            <div ref={bottomRef} />
          </div>
        )}

        {/* New comment input */}
        <div className="border-t border-[#f1f5f9] pt-4">
          <textarea
            ref={textareaRef}
            rows={3}
            placeholder="Add a note… (Ctrl+Enter to submit)"
            className="w-full rounded-lg border border-[#d1d9e0] bg-white px-3 py-2 text-sm text-[#0f172a] placeholder:text-[#94a3b8] focus:outline-none focus:border-[#0066cc] focus:ring-2 focus:ring-[#0066cc]/20 transition-all duration-150 resize-none"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <div className="flex justify-end mt-2">
            <Button
              size="sm"
              disabled={!draft.trim() || addMutation.isPending}
              onClick={() => addMutation.mutate(draft.trim())}
            >
              {addMutation.isPending
                ? <span className="flex items-center gap-1.5"><span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin"/>Posting…</span>
                : "Post comment"
              }
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
