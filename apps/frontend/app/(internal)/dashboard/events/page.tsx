"use client";
import React, { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEvents } from "../../../../hooks/useEvents";
import CreateEventModal from "../../../../components/events/CreateEventModal";

// Cursor: Event list page with create modal (Phase 2 Day 5)
export default function EventsPage() {
  const { data: events = [], isLoading, error } = useEvents();

  // Cursor: Modal open state
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  // Cursor: QueryClient สำหรับ invalidate cache หลัง create สำเร็จ
  const queryClient = useQueryClient();

  return (
    <div className="space-y-6">
      {/* Cursor: Header section + Create button */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">งานวิ่ง</h1>
          <p className="text-slate-600 mt-1">ดูและจัดการงานวิ่งทั้งหมด</p>
        </div>
        <button
          onClick={() => setIsCreateOpen(true)}
          className="bg-sky-600 text-white px-4 py-2 rounded hover:bg-sky-700 text-sm"
        >
          + สร้างงานใหม่
        </button>
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
          <p className="text-slate-500 text-sm mt-1">คลิก "สร้างงานใหม่" เพื่อเริ่มต้น</p>
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
                    {/* Cursor: ชื่องานเป็น Link ไป event detail */}
                    <td className="px-6 py-4">
                      <Link
                        href={`/dashboard/events/${event.id}`}
                        className="text-sky-600 hover:text-sky-700 hover:underline font-medium"
                      >
                        {event.name}
                      </Link>
                    </td>

                    <td className="px-6 py-4 text-slate-600 font-mono text-xs">
                      {event.organizer_id}
                    </td>

                    {/* Cursor: วันเริ่มต้น / สิ้นสุด */}
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

                    {/* Claude: ใช้ backend status (planned/active/completed) โดยตรง */}
                    <td className="px-6 py-4 text-center">
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded ${
                          event.status === "active"
                            ? "bg-green-100 text-green-700"
                            : event.status === "completed"
                              ? "bg-slate-100 text-slate-700"
                              : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {event.status === "active"
                          ? "กำลังดำเนิน"
                          : event.status === "completed"
                            ? "เสร็จสิ้น"
                            : "วางแผน"}
                      </span>
                    </td>

                    {/* Claude: checkpoints.length (Phase 3 จะ populate) */}
                    <td className="px-6 py-4 text-center text-slate-600">
                      {event.checkpoints.length > 0
                        ? `${event.checkpoints.length} แห่ง`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cursor: Create Event Modal — invalidate cache หลัง success */}
      <CreateEventModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={() =>
          queryClient.invalidateQueries({ queryKey: ["events"] })
        }
      />
    </div>
  );
}
