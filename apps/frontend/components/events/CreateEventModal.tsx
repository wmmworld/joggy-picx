"use client";
import React, { useEffect, useState } from "react";
import { apiPost } from "../../lib/api";
import type { Event, EventCreatePayload } from "../../hooks/useEvents";

// Cursor: Props สำหรับ CreateEventModal
interface CreateEventModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

// Cursor: Form state type แยกจาก payload เพราะ datetime-local ใช้ string local format
type FormState = {
  name: string;
  organizer_id: string;
  start_at: string;
  end_at: string;
  allowed_origins: string;
};

const EMPTY_FORM: FormState = {
  name: "",
  organizer_id: "",
  start_at: "",
  end_at: "",
  allowed_origins: ""
};

// Claude: แปลง datetime-local string → ISO UTC string
// datetime-local input ให้ "YYYY-MM-DDTHH:mm" ใน user's local time
// new Date() parse เป็น local; .toISOString() output เป็น UTC with Z
function toISOString(localDatetime: string): string {
  return new Date(localDatetime).toISOString();
}

// Cursor: Event Create Modal component — ไม่ใช้ shadcn Dialog, build เอง
export default function CreateEventModal({ isOpen, onClose, onSuccess }: CreateEventModalProps) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Cursor: Reset form ทุกครั้งที่ modal เปิด/ปิด
  useEffect(() => {
    if (!isOpen) {
      setForm(EMPTY_FORM);
      setValidationError(null);
      setApiError(null);
      setLoading(false);
    }
  }, [isOpen]);

  // Cursor: ไม่ render อะไรเมื่อ modal ปิด
  if (!isOpen) return null;

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    // Cursor: เคลียร์ validation error เมื่อ user แก้ไข field
    if (name === "end_at" || name === "start_at") {
      setValidationError(null);
    }
  };

  // Cursor: Backdrop click ปิด modal
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    // Cursor: Client-side validation — end_at ต้องมากกว่า start_at
    if (form.start_at && form.end_at) {
      if (new Date(form.end_at) <= new Date(form.start_at)) {
        setValidationError("วันสิ้นสุดต้องมากกว่าวันเริ่มต้น");
        return;
      }
    }

    // Cursor: Parse allowed_origins จาก textarea (optional)
    let allowedOriginsObj: object | null = null;
    if (form.allowed_origins.trim()) {
      try {
        allowedOriginsObj = JSON.parse(form.allowed_origins.trim());
      } catch {
        setValidationError('allowed_origins ต้องเป็น JSON ที่ถูกต้อง เช่น {"origins": ["https://example.com"]}');
        return;
      }
    }

    const payload: EventCreatePayload = {
      organizer_id: form.organizer_id.trim(),
      name: form.name.trim(),
      start_at: toISOString(form.start_at),
      end_at: toISOString(form.end_at),
      allowed_origins: allowedOriginsObj
    };

    setLoading(true);
    try {
      const result = await apiPost<Event, EventCreatePayload>("/internal/events", payload);

      if (!result.success) {
        setApiError(result.error || "ไม่สามารถสร้างงานได้ โปรดลองอีกครั้ง");
        return;
      }

      // Cursor: success → invalidate query แล้วปิด modal
      onSuccess();
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    // Cursor: Backdrop — fixed, z-50, ปิด modal เมื่อคลิกนอก card
    <div
      className="fixed inset-0 bg-black/50 z-50 overflow-y-auto"
      onClick={handleBackdropClick}
    >
      {/* Cursor: Modal card */}
      <div className="bg-white rounded-xl shadow-xl p-6 max-w-lg mx-auto mt-20 mb-10">
        {/* Cursor: Header row */}
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-xl font-bold">สร้างงานวิ่งใหม่</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-2xl leading-none"
            aria-label="ปิด"
          >
            ×
          </button>
        </div>

        {/* Cursor: API error banner */}
        {apiError && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            ⚠️ {apiError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Cursor: ชื่องาน */}
          <div>
            <label className="block text-sm font-medium mb-1">
              ชื่องาน <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="name"
              value={form.name}
              onChange={handleChange}
              required
              maxLength={255}
              placeholder="Bangkok Marathon 2026"
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
            />
          </div>

          {/* Cursor: Organizer ID */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Organizer ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              name="organizer_id"
              value={form.organizer_id}
              onChange={handleChange}
              required
              placeholder="UUID ของ Organizer"
              className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 font-mono"
            />
          </div>

          {/* Cursor: วันเริ่มต้น + สิ้นสุด อยู่บรรทัดเดียวกัน */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">
                เริ่มต้น <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                name="start_at"
                value={form.start_at}
                onChange={handleChange}
                required
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                สิ้นสุด <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                name="end_at"
                value={form.end_at}
                onChange={handleChange}
                required
                className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-400"
              />
            </div>
          </div>

          {/* Cursor: inline validation error สำหรับ date */}
          {validationError && (
            <p className="text-red-600 text-sm">{validationError}</p>
          )}

          {/* Cursor: Allowed Origins (optional JSON) */}
          <div>
            <label className="block text-sm font-medium mb-1">
              Allowed Origins{" "}
              <span className="text-slate-400 font-normal">(optional, JSON)</span>
            </label>
            <textarea
              name="allowed_origins"
              value={form.allowed_origins}
              onChange={handleChange}
              rows={3}
              placeholder={'{"origins": ["https://example.com"]}'}
              className="w-full border rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-400 resize-none"
            />
          </div>

          {/* Cursor: Action buttons */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-sm rounded border border-slate-300 hover:bg-slate-50 disabled:opacity-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-sm rounded bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "กำลังสร้าง..." : "สร้างงาน"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
