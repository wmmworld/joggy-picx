"use client";
import React, { useEffect, useState } from "react";
import { apiPatch } from "../../lib/api";

// Claude: minimal shape required for editing — accepts both Event (list) and EventDetail
interface EditableEvent {
  id: string;
  name: string;
  start_at: string;
  end_at: string;
  allowed_origins?: object | null;
}

interface EditEventModalProps {
  isOpen: boolean;
  event: EditableEvent;
  onClose: () => void;
  onSuccess: () => void;
}

// Claude: form values mirror datetime-local input (YYYY-MM-DDTHH:mm in local tz)
type FormState = {
  name: string;
  start_at: string;
  end_at: string;
  allowed_origins: string;
};

// Local time → ISO UTC (proper conversion)
function toISOString(localDatetime: string): string {
  return new Date(localDatetime).toISOString();
}

// Backend ISO (treat naive as UTC) → datetime-local input format ("YYYY-MM-DDTHH:mm")
function toLocalDatetimeInput(isoString: string): string {
  // Treat naive backend timestamps as UTC
  const hasTz = isoString.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(isoString);
  const d = new Date(hasTz ? isoString : isoString + "Z");
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export default function EditEventModal({ isOpen, event, onClose, onSuccess }: EditEventModalProps) {
  const [form, setForm] = useState<FormState>({
    name: event.name,
    start_at: toLocalDatetimeInput(event.start_at),
    end_at: toLocalDatetimeInput(event.end_at),
    allowed_origins: event.allowed_origins ? JSON.stringify(event.allowed_origins) : ""
  });
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Re-populate form when event prop changes (e.g., switching events)
  useEffect(() => {
    if (isOpen) {
      setForm({
        name: event.name,
        start_at: toLocalDatetimeInput(event.start_at),
        end_at: toLocalDatetimeInput(event.end_at),
        allowed_origins: event.allowed_origins ? JSON.stringify(event.allowed_origins) : ""
      });
      setValidationError(null);
      setApiError(null);
    }
  }, [isOpen, event]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    setValidationError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setApiError(null);

    if (!form.name.trim()) {
      setValidationError("กรุณากรอกชื่องาน");
      return;
    }
    if (!form.start_at || !form.end_at) {
      setValidationError("กรุณากรอกวันเริ่มและสิ้นสุด");
      return;
    }
    if (new Date(form.end_at) <= new Date(form.start_at)) {
      setValidationError("วันสิ้นสุดต้องอยู่หลังวันเริ่ม");
      return;
    }

    let parsedOrigins: object | null = null;
    if (form.allowed_origins.trim()) {
      try {
        parsedOrigins = JSON.parse(form.allowed_origins);
      } catch {
        setValidationError("Allowed Origins ต้องเป็น JSON ที่ถูกต้อง");
        return;
      }
    }

    setSubmitting(true);
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      start_at: toISOString(form.start_at),
      end_at: toISOString(form.end_at)
    };
    if (parsedOrigins !== null) {
      payload.allowed_origins = parsedOrigins;
    }

    const result = await apiPatch<EditableEvent>(`/internal/events/${event.id}`, payload);
    setSubmitting(false);

    if (!result.success) {
      setApiError(result.error || "บันทึกไม่สำเร็จ");
      return;
    }
    onSuccess();
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          <div className="flex justify-between items-start mb-4">
            <h2 className="text-2xl font-bold">แก้ไขงานวิ่ง</h2>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="text-slate-400 hover:text-slate-600 text-2xl leading-none disabled:opacity-50"
            >
              ×
            </button>
          </div>

          {(validationError || apiError) && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              ⚠️ {validationError || apiError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="edit-name" className="block text-sm font-medium text-slate-700 mb-1">
                ชื่องาน <span className="text-red-500">*</span>
              </label>
              <input
                id="edit-name"
                type="text"
                name="name"
                value={form.name}
                onChange={handleChange}
                required
                className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="edit-start" className="block text-sm font-medium text-slate-700 mb-1">
                  เริ่มต้น <span className="text-red-500">*</span>
                </label>
                <input
                  id="edit-start"
                  type="datetime-local"
                  name="start_at"
                  value={form.start_at}
                  onChange={handleChange}
                  required
                  className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
              <div>
                <label htmlFor="edit-end" className="block text-sm font-medium text-slate-700 mb-1">
                  สิ้นสุด <span className="text-red-500">*</span>
                </label>
                <input
                  id="edit-end"
                  type="datetime-local"
                  name="end_at"
                  value={form.end_at}
                  onChange={handleChange}
                  required
                  className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>
            </div>

            <div>
              <label htmlFor="edit-origins" className="block text-sm font-medium text-slate-700 mb-1">
                Allowed Origins <span className="text-slate-400 text-xs">(optional, JSON)</span>
              </label>
              <textarea
                id="edit-origins"
                name="allowed_origins"
                value={form.allowed_origins}
                onChange={handleChange}
                rows={3}
                placeholder='{"origins": ["https://example.com"]}'
                className="w-full px-3 py-2 border border-slate-300 rounded focus:outline-none focus:ring-2 focus:ring-sky-500 font-mono text-sm"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded hover:bg-slate-200 disabled:opacity-50"
              >
                ยกเลิก
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-sky-600 text-white rounded hover:bg-sky-700 disabled:opacity-50"
              >
                {submitting ? "กำลังบันทึก..." : "บันทึก"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
