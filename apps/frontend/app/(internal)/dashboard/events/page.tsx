"use client";
import React from "react";
import Link from "next/link";
import { useEvents } from "../../../../hooks/useEvents";

// Cursor: Event list page with table view (Phase 2)
export default function EventsPage() {
  // Cursor: Use custom hook for events list
  const { data: events = [], isLoading, error } = useEvents();

  return (
    <div className="space-y-6">
      {/* Cursor: Header section */}
      <div>
        <h1 className="text-3xl font-bold">งานวิ่ง</h1>
        <p className="text-slate-600 mt-1">ดูและจัดการงานวิ่งทั้งหมด</p>
      </div>

      {/* Cursor: Loading skeleton */}
      {isLoading && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="space-y-2 p-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-12 bg-slate-200 rounded animate-pulse" />
            ))}
          </div>
        </div>
      )}

      {/* Cursor: Error state */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          ⚠️ เกิดข้อผิดพลาดในการดึงข้อมูลงาน:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {/* Cursor: Empty state */}
      {!isLoading && events.length === 0 && !error && (
        <div className="p-12 text-center bg-slate-50 rounded border-2 border-dashed border-slate-300">
          <p className="text-slate-600 text-lg">ยังไม่มีงานวิ่ง</p>
          <p className="text-slate-500 text-sm mt-1">กรุณาติดต่อ admin เพื่อสร้างงานใหม่</p>
        </div>
      )}

      {/* Cursor: Events table */}
      {!isLoading && events.length > 0 && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              {/* Cursor: Table header */}
              <thead>
                <tr className="border-b bg-slate-50">
                  <th className="px-6 py-3 text-left font-semibold text-slate-700">ชื่องาน</th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-700">Organizer</th>
                  <th className="px-6 py-3 text-left font-semibold text-slate-700">วันจัดงาน</th>
                  <th className="px-6 py-3 text-center font-semibold text-slate-700">สถานะ</th>
                  <th className="px-6 py-3 text-center font-semibold text-slate-700">จุดถ่าย</th>
                </tr>
              </thead>

              {/* Cursor: Table body */}
              <tbody>
                {events.map((event, index) => (
                  <tr
                    key={event.id}
                    className={`border-b hover:bg-sky-50 transition-colors ${
                      index % 2 === 0 ? "bg-white" : "bg-slate-50"
                    }`}
                  >
                    {/* Cursor: Event name as clickable link */}
                    <td className="px-6 py-4">
                      <Link
                        href={`/dashboard/events/${event.id}`}
                        className="text-sky-600 hover:text-sky-700 hover:underline font-medium"
                      >
                        {event.name}
                      </Link>
                    </td>

                    {/* Cursor: Organizer ID */}
                    <td className="px-6 py-4 text-slate-600">{event.organizer_id}</td>

                    {/* Cursor: Event date range */}
                    <td className="px-6 py-4 text-slate-600">
                      <div className="space-y-1">
                        <p>
                          เริ่ม:{" "}
                          {new Date(event.start_at).toLocaleString("th-TH", {
                            dateStyle: "short",
                            timeStyle: "short"
                          })}
                        </p>
                        <p>
                          สิ้นสุด:{" "}
                          {new Date(event.end_at).toLocaleString("th-TH", {
                            dateStyle: "short",
                            timeStyle: "short"
                          })}
                        </p>
                      </div>
                    </td>

                    {/* Claude: use backend status (planned/active/completed) as authoritative source */}
                    <td className="px-6 py-4 text-center">
                      <span className={`px-2 py-1 text-xs font-medium rounded ${
                        event.status === "active" ? "bg-green-100 text-green-700" :
                        event.status === "completed" ? "bg-slate-100 text-slate-700" :
                        "bg-blue-100 text-blue-700"
                      }`}>
                        {event.status === "active" ? "กำลังดำเนิน" : event.status === "completed" ? "เสร็จสิ้น" : "วางแผน"}
                      </span>
                    </td>

                    {/* Claude: checkpoints.length (list endpoint returns empty array — Phase 3 will populate) */}
                    <td className="px-6 py-4 text-center text-slate-600">
                      {event.checkpoints.length > 0 ? `${event.checkpoints.length} แห่ง` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
