import React from "react";

// Cursor: Placeholder dashboard page that requires auth (Supabase)
export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <header className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold">Dashboard — Joggy-PicX</h1>
        <p className="text-sm text-slate-600 mt-1">
          {/* Cursor: Placeholder — this page must require authenticated Internal User (Supabase) */}
          หน้า dashboard สำหรับ Admin / Staff — การยืนยันตัวตน (MFA) จะต่อใน Phase 2
        </p>
      </header>
      <main className="max-w-6xl mx-auto mt-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="col-span-2">
            <section className="bg-white rounded shadow p-4">Placeholder: event list / review queue</section>
          </div>
          <aside className="bg-white rounded shadow p-4">Placeholder: quick actions</aside>
        </div>
      </main>
    </div>
  );
}
