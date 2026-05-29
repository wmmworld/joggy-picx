"use client";
import React from "react";

// Cursor: Manual Review Queue page — Phase 2 Day 5 skeleton (no API calls yet)
export default function ReviewQueuePage() {
  return (
    <div className="space-y-6">
      {/* Cursor: Header section */}
      <div>
        <h1 className="text-3xl font-bold">คิวตรวจสอบรูป</h1>
        <p className="text-slate-600 mt-1">
          รูปที่ AI ประเมิน confidence ต่ำ รอการตรวจสอบจาก staff
        </p>
      </div>

      {/* Cursor: Stats card + action buttons */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <p className="text-sm text-slate-500 mb-1">รูปรอตรวจสอบ</p>
            <p className="text-4xl font-bold text-sky-600">0</p>
          </div>
          <div className="flex gap-2">
            <button
              disabled
              className="px-4 py-2 bg-green-100 text-green-700 rounded hover:bg-green-200 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
            >
              อนุมัติ
            </button>
            <button
              disabled
              className="px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
            >
              ปฏิเสธ
            </button>
          </div>
        </div>
      </div>

      {/* Cursor: Review queue table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            {/* Cursor: Table header */}
            <thead>
              <tr className="border-b bg-slate-50">
                <th className="px-6 py-3 text-left font-semibold text-slate-700">รูปภาพ</th>
                <th className="px-6 py-3 text-left font-semibold text-slate-700">เลขบิบ</th>
                <th className="px-6 py-3 text-left font-semibold text-slate-700">งาน</th>
                <th className="px-6 py-3 text-center font-semibold text-slate-700">
                  AI Confidence
                </th>
                <th className="px-6 py-3 text-center font-semibold text-slate-700">การจัดการ</th>
              </tr>
            </thead>

            {/* Cursor: Table body — empty state (Phase 3 will populate) */}
            <tbody>
              <tr className="border-b bg-white hover:bg-sky-50 transition-colors">
                <td colSpan={5} className="px-6 py-12 text-center text-slate-500">
                  <p className="text-base">ยังไม่มีรูปรอตรวจสอบ ✓</p>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Cursor: Footer note — Phase 3 placeholder */}
        <div className="bg-slate-50 px-6 py-3 border-t text-xs text-slate-500">
          🔜 <span className="font-medium">Phase 3:</span> ระบบ AI จะส่งรูปที่ confidence
          ต่ำกว่า 80% มาที่นี่โดยอัตโนมัติ
        </div>
      </div>
    </div>
  );
}
