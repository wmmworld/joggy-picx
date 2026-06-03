"use client";
import React from "react";
import Link from "next/link";

// Cursor: Main dashboard page (Phase 2) — nav cards + quick actions
export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-6">
      <header className="max-w-6xl mx-auto">
        <h1 className="text-2xl md:text-3xl font-bold">Dashboard</h1>
        <p className="text-sm text-slate-600 mt-1">
          {/* Cursor: Internal User dashboard — Admin/Staff only */}
          หน้าหลัก Joggy-PicX สำหรับ Admin / Staff
        </p>
      </header>

      <main className="max-w-6xl mx-auto mt-8">
        {/* Cursor: Navigation cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Cursor: Events card */}
          <Link href="/dashboard/events" className="group">
            <div className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-6 h-full border-l-4 border-sky-500">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-lg group-hover:text-sky-600 transition-colors">
                  งานวิ่ง
                </h3>
                <span className="text-2xl">🏃</span>
              </div>
              <p className="text-sm text-slate-600">สร้าง จัดการ ดูรายละเอียดงาน</p>
            </div>
          </Link>

          {/* Cursor: Review Queue card */}
          <Link href="/dashboard/review" className="group">
            <div className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-6 h-full border-l-4 border-orange-500">
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-semibold text-lg group-hover:text-orange-600 transition-colors">
                  คิวตรวจสอบ
                </h3>
                <span className="text-2xl">👀</span>
              </div>
              <p className="text-sm text-slate-600">รูปรอการตรวจสอบจาก AI</p>
              {/* Cursor: Pending badge (hardcoded 0 for Phase 2) */}
              <div className="mt-4">
                <span className="px-2 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded">
                  0 รูป
                </span>
              </div>
            </div>
          </Link>

          {/* Cursor: Quick actions card */}
          <div className="bg-white rounded-lg shadow p-6 h-full border-l-4 border-slate-300">
            <div className="flex items-start justify-between mb-2">
              <h3 className="font-semibold text-lg">เมนูอื่น ๆ</h3>
              <span className="text-2xl">⚙️</span>
            </div>
            <p className="text-sm text-slate-600 mb-4">คุณลักษณะเพิ่มเติม</p>
            <div className="space-y-2">
              <button
                disabled
                className="w-full px-3 py-2 text-sm bg-slate-100 text-slate-500 rounded cursor-not-allowed"
              >
                จัดการ Partner
              </button>
              <button
                disabled
                className="w-full px-3 py-2 text-sm bg-slate-100 text-slate-500 rounded cursor-not-allowed"
              >
                ผู้ใช้งาน
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
