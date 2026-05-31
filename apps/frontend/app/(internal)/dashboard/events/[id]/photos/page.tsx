"use client";
import React, { useState, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useEventDetail } from "../../../../../../hooks/useEventDetail";
import { useEventPhotos, type PhotoItem } from "../../../../../../hooks/useEventPhotos";

// Cursor: Photo Gallery page — Phase 4C
export default function EventPhotosPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();

  const eventId = params.id as string;
  const page = Number.parseInt(searchParams.get("page") || "1", 10);
  const bib = searchParams.get("bib") || "";
  const checkpointId = searchParams.get("checkpoint_id") || "";
  const aiStatus = searchParams.get("ai_status") || "";

  // Cursor: Local state for debounced bib input + lightbox
  const [bibInput, setBibInput] = useState(bib);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  // Cursor: Fetch event detail (for name + checkpoints) + photos
  const { data: event } = useEventDetail(eventId);
  const { data: photosData, isLoading } = useEventPhotos(eventId, {
    page,
    bib,
    checkpointId,
    aiStatus,
  });

  // Cursor: Debounce bib input 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      if (bibInput !== bib) {
        updateFilters({ bib: bibInput, page: 1 });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [bibInput]);

  // Cursor: Sync bibInput with URL bib when URL changes externally
  useEffect(() => {
    setBibInput(bib);
  }, [bib]);

  // Cursor: Update URL search params
  const updateFilters = (updates: {
    page?: number;
    bib?: string;
    checkpointId?: string;
    aiStatus?: string;
  }) => {
    const params = new URLSearchParams(searchParams.toString());
    if (updates.page !== undefined) params.set("page", String(updates.page));
    if (updates.bib !== undefined) {
      if (updates.bib) {
        params.set("bib", updates.bib);
      } else {
        params.delete("bib");
      }
    }
    if (updates.checkpointId !== undefined) {
      if (updates.checkpointId) {
        params.set("checkpoint_id", updates.checkpointId);
      } else {
        params.delete("checkpoint_id");
      }
    }
    if (updates.aiStatus !== undefined) {
      if (updates.aiStatus) {
        params.set("ai_status", updates.aiStatus);
      } else {
        params.delete("ai_status");
      }
    }
    router.push(`/dashboard/events/${eventId}/photos?${params.toString()}`);
  };

  // Cursor: Clear all filters
  const clearFilters = () => {
    setBibInput("");
    router.push(`/dashboard/events/${eventId}/photos`);
  };

  // Cursor: Check if any filter is active
  const hasActiveFilters = bib || checkpointId || aiStatus;

  // Cursor: Pagination helpers
  const goToPage = (newPage: number) => {
    updateFilters({ page: newPage });
  };

  return (
    <div className="space-y-6">
      {/* Cursor: Back link + header */}
      <div>
        <Link
          href={`/dashboard/events/${eventId}`}
          className="inline-flex items-center gap-1 text-sm text-sky-600 hover:text-sky-700 mb-2"
        >
          ← กลับ Event Detail
        </Link>
        <h1 className="text-3xl font-bold">ภาพถ่าย</h1>
        {event && <p className="text-slate-600 mt-1">{event.name}</p>}
      </div>

      {/* Cursor: Filter bar */}
      <div className="bg-white rounded-lg shadow p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          {/* Cursor: Bib search input */}
          <div>
            <input
              type="text"
              placeholder="🔍 ค้นหาบิบ..."
              value={bibInput}
              onChange={(e) => setBibInput(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500 text-sm"
            />
          </div>

          {/* Cursor: Checkpoint select */}
          <div>
            <select
              value={checkpointId}
              onChange={(e) => updateFilters({ checkpointId: e.target.value, page: 1 })}
              className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500 text-sm"
            >
              <option value="">ทุกจุด</option>
              {event?.checkpoints?.map((cp) => (
                <option key={cp.id} value={cp.id}>
                  {cp.name}
                </option>
              ))}
            </select>
          </div>

          {/* Cursor: AI Status select */}
          <div>
            <select
              value={aiStatus}
              onChange={(e) => updateFilters({ aiStatus: e.target.value, page: 1 })}
              className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500 text-sm"
            >
              <option value="">สถานะทั้งหมด</option>
              <option value="auto">✅ AI อนุมัติ</option>
              <option value="manual_pending">⏳ รอตรวจสอบ</option>
              <option value="manual_approved">✓ Staff อนุมัติ</option>
              <option value="manual_rejected">✗ Staff ปฏิเสธ</option>
            </select>
          </div>

          {/* Cursor: Clear filter button */}
          {hasActiveFilters && (
            <div>
              <button
                onClick={clearFilters}
                className="w-full px-3 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 text-sm font-medium"
              >
                ล้าง filter
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Cursor: Stats bar */}
      {photosData && (
        <div className="text-sm text-slate-600">
          แสดง{" "}
          <span className="font-medium">
            {(photosData.page - 1) * photosData.per_page + 1}–
            {Math.min(photosData.page * photosData.per_page, photosData.total)}
          </span>{" "}
          จาก <span className="font-medium">{photosData.total}</span> รูป
        </div>
      )}

      {/* Cursor: Loading skeleton */}
      {isLoading ? (
        <div className="grid grid-cols-3 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg overflow-hidden shadow">
              <div className="aspect-square bg-slate-200 animate-pulse" />
              <div className="p-2 space-y-2">
                <div className="h-4 bg-slate-200 rounded animate-pulse" />
                <div className="h-3 bg-slate-200 rounded animate-pulse w-2/3" />
              </div>
            </div>
          ))}
        </div>
      ) : photosData && photosData.items.length === 0 ? (
        // Cursor: Empty state
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <p className="text-slate-500 mb-4">ไม่พบรูปภาพ</p>
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="px-4 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 text-sm font-medium"
            >
              ล้าง filter
            </button>
          )}
        </div>
      ) : (
        // Cursor: Photo grid
        <>
          <div className="grid grid-cols-3 md:grid-cols-4 gap-4">
            {photosData?.items.map((photo) => (
              <PhotoCard
                key={photo.photo_id}
                photo={photo}
                onImageClick={(url) => setLightboxUrl(url)}
              />
            ))}
          </div>

          {/* Cursor: Pagination bar */}
          {photosData && photosData.pages > 1 && (
            <PaginationBar
              currentPage={photosData.page}
              totalPages={photosData.pages}
              onPageChange={goToPage}
            />
          )}
        </>
      )}

      {/* Cursor: Lightbox modal */}
      {lightboxUrl && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => setLightboxUrl(null)}
        >
          <img
            src={lightboxUrl}
            alt="Full size"
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}

// Cursor: Photo card component
function PhotoCard({
  photo,
  onImageClick,
}: {
  photo: PhotoItem;
  onImageClick: (url: string) => void;
}) {
  return (
    <div className="bg-white rounded-lg overflow-hidden shadow hover:shadow-md transition-shadow cursor-pointer">
      {/* Cursor: Thumbnail */}
      <div className="aspect-square bg-slate-100 relative">
        {photo.thumbnail_url ? (
          <img
            src={photo.thumbnail_url}
            alt="photo"
            className="w-full h-full object-cover"
            onClick={() => onImageClick(photo.thumbnail_url!)}
            onError={(e) => {
              e.currentTarget.style.display = "none";
              e.currentTarget.parentElement!.innerHTML = `
                <div class="w-full h-full flex items-center justify-center text-4xl">
                  📷
                </div>
              `;
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-4xl">📷</div>
        )}
      </div>

      {/* Cursor: Info */}
      <div className="p-2 space-y-1">
        <div className="flex items-center justify-between">
          <span className="font-medium text-sm">{photo.bib_number || "ไม่พบ"}</span>
          <ConfidenceBadge confidence={photo.bib_confidence} />
        </div>
        <AIStatusBadge status={photo.ai_review_status} />
        {photo.checkpoint_name && (
          <p className="text-xs text-slate-500">{photo.checkpoint_name}</p>
        )}
      </div>
    </div>
  );
}

// Cursor: Confidence badge component
function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  let className = "px-2 py-0.5 text-xs font-medium rounded ";
  let text = "—";

  if (confidence !== null) {
    text = `${Math.round(confidence * 100)}%`;
    if (confidence >= 0.7) {
      className += "bg-green-100 text-green-700";
    } else if (confidence >= 0.5) {
      className += "bg-yellow-100 text-yellow-700";
    } else {
      className += "bg-red-100 text-red-700";
    }
  } else {
    className += "bg-slate-100 text-slate-500";
  }

  return <span className={className}>{text}</span>;
}

// Cursor: AI status badge component
function AIStatusBadge({
  status,
}: {
  status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected";
}) {
  const config = {
    auto: { label: "✅ AI", className: "bg-green-100 text-green-700" },
    manual_pending: { label: "⏳ รอ", className: "bg-yellow-100 text-yellow-700" },
    manual_approved: { label: "✓ อนุมัติ", className: "bg-green-100 text-green-700" },
    manual_rejected: { label: "✗ ปฏิเสธ", className: "bg-red-100 text-red-700" },
  };

  const { label, className } = config[status];

  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded ${className}`}>
      {label}
    </span>
  );
}

// Cursor: Pagination bar component
function PaginationBar({
  currentPage,
  totalPages,
  onPageChange,
}: {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  // Cursor: Generate page numbers to display (max 7 buttons)
  const getPageNumbers = () => {
    const pages: (number | string)[] = [];
    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      pages.push(1);
      if (currentPage > 3) pages.push("...");
      for (
        let i = Math.max(2, currentPage - 1);
        i <= Math.min(totalPages - 1, currentPage + 1);
        i++
      ) {
        pages.push(i);
      }
      if (currentPage < totalPages - 2) pages.push("...");
      pages.push(totalPages);
    }
    return pages;
  };

  return (
    <div className="flex items-center justify-center gap-2">
      {/* Cursor: Previous button */}
      <button
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
        className="px-3 py-1 bg-white border border-slate-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
      >
        ←
      </button>

      {/* Cursor: Page numbers */}
      {getPageNumbers().map((pageNum, i) =>
        typeof pageNum === "number" ? (
          <button
            key={i}
            onClick={() => onPageChange(pageNum)}
            className={`px-3 py-1 rounded text-sm font-medium ${
              currentPage === pageNum
                ? "bg-sky-600 text-white"
                : "bg-white border border-slate-300 hover:bg-slate-50"
            }`}
          >
            {pageNum}
          </button>
        ) : (
          <span key={i} className="px-2 text-slate-400">
            {pageNum}
          </span>
        )
      )}

      {/* Cursor: Next button */}
      <button
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="px-3 py-1 bg-white border border-slate-300 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
      >
        →
      </button>
    </div>
  );
}
