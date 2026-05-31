"use client";
import React, { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useEventDetail } from "../../../../../hooks/useEventDetail";
import { formatThaiDateTime } from "../../../../../lib/datetime";
import { apiDelete } from "../../../../../lib/api";
import EditEventModal from "../../../../../components/events/EditEventModal";

// Cursor: Event detail page with custom hook (Phase 2)
export default function EventDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const eventId = params.id as string;

  // Cursor: Use custom hook for event detail
  const { data: event, isLoading, error } = useEventDetail(eventId || null);

  // Claude: Edit + Delete state
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError(null);
    const result = await apiDelete(`/internal/events/${eventId}`);
    setDeleting(false);
    if (!result.success) {
      setDeleteError(result.error || "ลบไม่สำเร็จ");
      return;
    }
    // Invalidate events list + navigate back
    queryClient.invalidateQueries({ queryKey: ["events"] });
    router.push("/dashboard/events");
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 bg-slate-200 rounded w-1/3 animate-pulse" />
        <div className="h-40 bg-slate-200 rounded animate-pulse" />
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-slate-200 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="space-y-4">
        <Link href="/dashboard/events" className="text-sky-600 hover:underline">
          ← กลับไปยังรายการงาน
        </Link>
        <div className="p-6 bg-red-50 border border-red-200 rounded text-red-700">
          <p className="font-semibold">ไม่สามารถโหลดข้อมูลงาน</p>
          <p className="text-sm mt-2">
            {error instanceof Error ? error.message : "Unknown error"}
          </p>
        </div>
      </div>
    );
  }

  // Cursor: Calculate event status
  const now = new Date();
  const start = new Date(event.start_at);
  const end = new Date(event.end_at);
  const isOngoing = now >= start && now <= end;
  const isCompleted = now > end;

  return (
    <div className="space-y-6">
      {/* Claude: Top navigation — Dashboard + Events list */}
      <div className="flex items-center gap-3 text-sm">
        <Link href="/dashboard" className="text-sky-600 hover:underline">
          ← Dashboard
        </Link>
        <span className="text-slate-300">/</span>
        <Link href="/dashboard/events" className="text-sky-600 hover:underline">
          รายการงาน
        </Link>
      </div>

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold">{event.name}</h1>
            <p className="text-slate-600 mt-1">Event ID: {event.id}</p>
            <p className="text-slate-600 text-sm">Organizer: {event.organizer_id}</p>
          </div>
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              isOngoing
                ? "bg-green-100 text-green-700"
                : isCompleted
                  ? "bg-slate-100 text-slate-700"
                  : "bg-blue-100 text-blue-700"
            }`}
          >
            {isOngoing ? "กำลังดำเนิน" : isCompleted ? "เสร็จสิ้น" : "รอเริ่มต้น"}
          </span>
        </div>

        {/* Claude: event.description not in EventOut — Phase 3+ field, omit for now */}

        {/* Cursor: Photo Gallery link button — Phase 4C */}
        <div className="mt-4">
          <Link
            href={`/dashboard/events/${eventId}/photos`}
            className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 text-sm font-medium"
          >
            📷 ดูรูปภาพ
          </Link>
        </div>

        {/* Cursor: Event timeline */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6 pt-6 border-t">
          <div>
            <p className="text-slate-500 text-sm">เริ่มต้น</p>
            <p className="font-semibold">
              {formatThaiDateTime(event.start_at)}
            </p>
          </div>
          <div>
            <p className="text-slate-500 text-sm">สิ้นสุด</p>
            <p className="font-semibold">
              {formatThaiDateTime(event.end_at)}
            </p>
          </div>
          <div>
            <p className="text-slate-500 text-sm">จุดถ่าย</p>
            {/* Claude: photo_count / pending_review Phase 3+ — แสดง checkpoint count แทน */}
            <p className="font-semibold text-lg">{event.checkpoints.length}</p>
          </div>
        </div>
      </div>

      {/* Cursor: Checkpoints section */}
      {event.checkpoints && event.checkpoints.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">จุดถ่าย ({event.checkpoints.length})</h2>
          <div className="space-y-3">
            {/* Claude: sort by seq_order (backend field); location → lat/lng if available */}
            {event.checkpoints
              .sort((a, b) => a.seq_order - b.seq_order)
              .map((cp) => (
                <div key={cp.id} className="flex items-start space-x-3 p-3 bg-slate-50 rounded">
                  <div className="flex-shrink-0 w-8 h-8 bg-sky-500 text-white rounded-full flex items-center justify-center text-sm font-semibold">
                    {cp.seq_order}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{cp.name}</p>
                    <p className="text-xs text-slate-500 uppercase tracking-wide">{cp.kind}</p>
                    {cp.lat != null && cp.lng != null && (
                      <p className="text-sm text-slate-600">📍 {cp.lat.toFixed(5)}, {cp.lng.toFixed(5)}</p>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Claude: Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={() => setShowEditModal(true)}
          className="px-4 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 border border-slate-300"
        >
          ✏️ แก้ไขงาน
        </button>
        <button
          onClick={() => setShowDeleteConfirm(true)}
          className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
        >
          🗑️ ลบงาน
        </button>
      </div>

      {/* Claude: Edit modal */}
      {showEditModal && (
        <EditEventModal
          isOpen={showEditModal}
          event={event}
          onClose={() => setShowEditModal(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["event", eventId] });
            queryClient.invalidateQueries({ queryKey: ["events"] });
            setShowEditModal(false);
          }}
        />
      )}

      {/* Claude: Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => !deleting && setShowDeleteConfirm(false)}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-bold mb-2">ยืนยันการลบงาน</h2>
            <p className="text-slate-600 mb-2">
              คุณกำลังจะลบ <strong>{event.name}</strong>
            </p>
            <div className="bg-red-50 border border-red-200 rounded p-3 mb-4 text-sm text-red-700">
              ⚠️ การลบจะลบข้อมูลทั้งหมดที่เกี่ยวข้องอย่างถาวร:
              <ul className="list-disc list-inside mt-1">
                <li>รูปภาพทั้งหมดของงานนี้</li>
                <li>Checkpoints + Event Tokens</li>
                <li>Review Queue + Face Embeddings</li>
              </ul>
              ไม่สามารถกู้คืนได้
            </div>
            {deleteError && (
              <div className="bg-red-100 border border-red-300 rounded p-2 mb-3 text-sm text-red-800">
                {deleteError}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? "กำลังลบ..." : "ยืนยันลบ"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
