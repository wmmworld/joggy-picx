"use client";
import React, { useState, useEffect } from "react";
import { useEvents } from "../../../../hooks/useEvents";
import { useReviewQueue, useResolveItem, type ReviewQueueItem } from "../../../../hooks/useReviewQueue";

// Cursor: Manual Review Queue page — Phase 4B full implementation
export default function ReviewQueuePage() {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [overrideBibs, setOverrideBibs] = useState<Record<string, string>>({});
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // Cursor: Fetch events for dropdown + review queue items for selected event
  const { data: events = [], isLoading: eventsLoading } = useEvents();
  const { data: queueData, isLoading: queueLoading } = useReviewQueue(selectedEventId);
  const resolveItem = useResolveItem();

  // Cursor: Initialize items from API data
  useEffect(() => {
    if (queueData) setItems(queueData);
  }, [queueData]);

  // Cursor: Toast helper — show message for 3s
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  // Cursor: Handle per-item approve
  const handleApprove = async (queueId: string) => {
    setProcessingIds((prev) => new Set(prev).add(queueId));
    try {
      await resolveItem.mutateAsync({
        queueId,
        payload: {
          action: "approve",
          decision_bib: overrideBibs[queueId]?.trim() || null,
        },
      });
      setItems((prev) => prev.filter((item) => item.queue_id !== queueId));
      setSelectedItems((prev) => {
        const next = new Set(prev);
        next.delete(queueId);
        return next;
      });
      showToast("อนุมัติแล้ว", "success");
    } catch (error) {
      showToast("เกิดข้อผิดพลาด กรุณาลองใหม่", "error");
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev);
        next.delete(queueId);
        return next;
      });
    }
  };

  // Cursor: Handle per-item reject
  const handleReject = async (queueId: string) => {
    setProcessingIds((prev) => new Set(prev).add(queueId));
    try {
      await resolveItem.mutateAsync({
        queueId,
        payload: { action: "reject" },
      });
      setItems((prev) => prev.filter((item) => item.queue_id !== queueId));
      setSelectedItems((prev) => {
        const next = new Set(prev);
        next.delete(queueId);
        return next;
      });
      showToast("ปฏิเสธแล้ว", "success");
    } catch (error) {
      showToast("เกิดข้อผิดพลาด กรุณาลองใหม่", "error");
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev);
        next.delete(queueId);
        return next;
      });
    }
  };

  // Cursor: Bulk approve selected items
  const handleBulkApprove = async () => {
    const ids = Array.from(selectedItems);
    try {
      await Promise.all(
        ids.map((queueId) =>
          resolveItem.mutateAsync({
            queueId,
            payload: { action: "approve" },
          })
        )
      );
      setItems((prev) => prev.filter((item) => !selectedItems.has(item.queue_id)));
      setSelectedItems(new Set());
      showToast(`อนุมัติ ${ids.length} รายการแล้ว`, "success");
    } catch (error) {
      showToast("เกิดข้อผิดพลาดบางรายการ กรุณาตรวจสอบ", "error");
    }
  };

  // Cursor: Bulk reject selected items
  const handleBulkReject = async () => {
    const ids = Array.from(selectedItems);
    try {
      await Promise.all(
        ids.map((queueId) =>
          resolveItem.mutateAsync({
            queueId,
            payload: { action: "reject" },
          })
        )
      );
      setItems((prev) => prev.filter((item) => !selectedItems.has(item.queue_id)));
      setSelectedItems(new Set());
      showToast(`ปฏิเสธ ${ids.length} รายการแล้ว`, "success");
    } catch (error) {
      showToast("เกิดข้อผิดพลาดบางรายการ กรุณาตรวจสอบ", "error");
    }
  };

  // Cursor: Toggle individual checkbox
  const toggleSelect = (queueId: string) => {
    setSelectedItems((prev) => {
      const next = new Set(prev);
      if (next.has(queueId)) {
        next.delete(queueId);
      } else {
        next.add(queueId);
      }
      return next;
    });
  };

  // Cursor: Toggle select all
  const toggleSelectAll = () => {
    if (selectedItems.size === items.length) {
      setSelectedItems(new Set());
    } else {
      setSelectedItems(new Set(items.map((item) => item.queue_id)));
    }
  };

  // Cursor: Confidence badge color helper
  const getConfidenceBadgeClass = (confidence: number | null) => {
    if (confidence === null || confidence < 0.5) return "bg-red-100 text-red-700";
    if (confidence < 0.7) return "bg-yellow-100 text-yellow-700";
    return "bg-green-100 text-green-700";
  };

  // Cursor: Format date helper (DD/MM/YYYY)
  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
  };

  return (
    <div className="space-y-6">
      {/* Cursor: Header section */}
      <div>
        <h1 className="text-3xl font-bold">คิวตรวจสอบรูป</h1>
        <p className="text-slate-600 mt-1">
          รูปที่ AI ประเมิน confidence ต่ำ รอการตรวจสอบจาก staff
        </p>
      </div>

      {/* Cursor: Event selector dropdown */}
      <div className="bg-white rounded-lg shadow p-4">
        <label htmlFor="event-select" className="block text-sm font-medium text-slate-700 mb-2">
          เลือกงานวิ่ง
        </label>
        <select
          id="event-select"
          className="w-full md:w-96 px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500"
          value={selectedEventId || ""}
          onChange={(e) => {
            setSelectedEventId(e.target.value || null);
            setSelectedItems(new Set());
            setOverrideBibs({});
          }}
        >
          {eventsLoading ? (
            <option disabled>กำลังโหลด...</option>
          ) : (
            <>
              <option value="">— เลือกงานวิ่ง —</option>
              {events.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.name} ({formatDate(event.start_at)})
                </option>
              ))}
            </>
          )}
        </select>
      </div>

      {/* Cursor: Stats bar — only when event selected and data loaded */}
      {selectedEventId && !queueLoading && (
        <div className="bg-white rounded-lg shadow p-4">
          <div className="flex flex-wrap gap-2">
            <span className="px-3 py-1 bg-sky-100 text-sky-700 text-sm font-medium rounded">
              {items.length} รูปรอตรวจสอบ
            </span>
          </div>
        </div>
      )}

      {/* Cursor: Bulk action bar — only when items selected */}
      {selectedItems.size >= 1 && (
        <div className="bg-sky-50 border border-sky-200 rounded-lg p-4 flex items-center justify-between">
          <span className="text-sm font-medium text-sky-900">
            ☑ {selectedItems.size} รายการที่เลือก
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleBulkApprove}
              className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm font-medium"
            >
              ✓ Approve all
            </button>
            <button
              onClick={handleBulkReject}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-medium"
            >
              ✗ Reject all
            </button>
          </div>
        </div>
      )}

      {/* Cursor: Table or empty states */}
      {!selectedEventId ? (
        // Cursor: No event selected state
        <div className="bg-white rounded-lg shadow p-12 text-center text-slate-500">
          <p className="text-base">กรุณาเลือกงานวิ่ง</p>
        </div>
      ) : queueLoading ? (
        // Cursor: Loading skeleton
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b bg-slate-50">
                  <th className="px-4 py-3 text-left font-semibold text-slate-700 w-12">☐</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">รูปภาพ</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">บิบ + override</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">สาเหตุ</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">จุดถ่าย</th>
                  <th className="px-4 py-3 text-center font-semibold text-slate-700">การจัดการ</th>
                </tr>
              </thead>
            <tbody>
              {[1, 2, 3].map((i) => (
                <tr key={i} className="border-b">
                  <td className="px-4 py-4">
                    <div className="w-4 h-4 bg-slate-200 rounded animate-pulse" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="w-16 h-16 bg-slate-200 rounded animate-pulse" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="w-20 h-4 bg-slate-200 rounded animate-pulse" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="w-16 h-4 bg-slate-200 rounded animate-pulse" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="w-24 h-4 bg-slate-200 rounded animate-pulse" />
                  </td>
                  <td className="px-4 py-4">
                    <div className="w-16 h-4 bg-slate-200 rounded animate-pulse mx-auto" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : items.length === 0 ? (
        // Cursor: Empty state — no items
        <div className="bg-white rounded-lg shadow p-12 text-center text-slate-500">
          <p className="text-base">ไม่มีรูปรอตรวจสอบ ✓</p>
        </div>
      ) : (
        // Cursor: Main table with data
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b bg-slate-50">
                  <th className="px-4 py-3 text-left font-semibold text-slate-700 w-12">
                    <input
                      type="checkbox"
                      checked={items.length > 0 && selectedItems.size === items.length}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 cursor-pointer"
                    />
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">รูปภาพ</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">บิบ + override</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">สาเหตุ</th>
                  <th className="px-4 py-3 text-left font-semibold text-slate-700">จุดถ่าย</th>
                  <th className="px-4 py-3 text-center font-semibold text-slate-700">การจัดการ</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const isProcessing = processingIds.has(item.queue_id);
                  return (
                    <tr key={item.queue_id} className="border-b hover:bg-slate-50 transition-colors">
                      {/* Cursor: Checkbox column */}
                      <td className="px-4 py-4">
                        <input
                          type="checkbox"
                          checked={selectedItems.has(item.queue_id)}
                          onChange={() => toggleSelect(item.queue_id)}
                          className="w-4 h-4 cursor-pointer"
                        />
                      </td>

                      {/* Cursor: รูปภาพ column — thumbnail with lightbox */}
                      <td className="px-4 py-4">
                        {item.thumbnail_url ? (
                          <img
                            src={item.thumbnail_url}
                            alt="Thumbnail"
                            className="w-16 h-16 object-cover rounded cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => setLightboxUrl(item.thumbnail_url)}
                            onError={(e) => {
                              e.currentTarget.style.display = "none";
                              e.currentTarget.parentElement!.innerHTML = `
                                <div class="w-16 h-16 bg-slate-200 rounded flex items-center justify-center text-2xl">
                                  📷
                                </div>
                              `;
                            }}
                          />
                        ) : (
                          <div className="w-16 h-16 bg-slate-200 rounded flex items-center justify-center text-2xl">
                            📷
                          </div>
                        )}
                      </td>

                      {/* Cursor: บิบ column — AI bib + confidence + override input */}
                      <td className="px-4 py-4">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-900">
                              {item.bib_number || "ไม่พบ"}
                            </span>
                            <span
                              className={`px-2 py-0.5 text-xs font-medium rounded ${getConfidenceBadgeClass(item.bib_confidence)}`}
                            >
                              {item.bib_confidence !== null
                                ? `${Math.round(item.bib_confidence * 100)}%`
                                : "—"}
                            </span>
                          </div>
                          <input
                            type="text"
                            placeholder="แก้ไขบิบ (optional)"
                            value={overrideBibs[item.queue_id] || ""}
                            onChange={(e) =>
                              setOverrideBibs((prev) => ({
                                ...prev,
                                [item.queue_id]: e.target.value,
                              }))
                            }
                            className="w-full px-2 py-1 text-xs border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-sky-500"
                          />
                        </div>
                      </td>

                      {/* Cursor: สาเหตุ column — reason badge */}
                      <td className="px-4 py-4">
                        {item.reason === "low_ocr_conf" ? (
                          <span className="px-2 py-1 bg-yellow-100 text-yellow-700 text-xs font-medium rounded">
                            OCR ต่ำ
                          </span>
                        ) : (
                          <span className="px-2 py-1 bg-red-100 text-red-700 text-xs font-medium rounded">
                            ไม่พบบิบ
                          </span>
                        )}
                      </td>

                      {/* Cursor: จุดถ่าย column */}
                      <td className="px-4 py-4 text-slate-700">
                        {item.checkpoint_name || "—"}
                      </td>

                      {/* Cursor: การจัดการ column — approve/reject buttons */}
                      <td className="px-4 py-4">
                        <div className="flex items-center justify-center gap-2">
                          <button
                            onClick={() => handleApprove(item.queue_id)}
                            disabled={isProcessing}
                            className="px-3 py-1 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-medium"
                          >
                            {isProcessing ? "..." : "✓"}
                          </button>
                          <button
                            onClick={() => handleReject(item.queue_id)}
                            disabled={isProcessing}
                            className="px-3 py-1 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed text-xs font-medium"
                          >
                            {isProcessing ? "..." : "✗"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cursor: Lightbox modal — click backdrop to close */}
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

      {/* Cursor: Toast notification — bottom-right, auto-hide 3s */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium z-50 ${
            toast.type === "success" ? "bg-green-600" : "bg-red-600"
          }`}
        >
          {toast.message}
        </div>
      )}
    </div>
  );
}
