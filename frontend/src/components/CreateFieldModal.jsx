import { useState } from "react";
import Modal from "./Modal.jsx";
import { createCanonicalField } from "../api.js";

// polarity is income|deduction only — identity fields (employee_id/name) are
// system metadata and are never created through this UI (the API rejects them).
export default function CreateFieldModal({ onClose, onCreated }) {
  const [key, setKey] = useState("");
  const [aliases, setAliases] = useState("");
  const [expectedGroup, setExpectedGroup] = useState("");
  const [polarity, setPolarity] = useState("income");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const field = await createCanonicalField({
        key: key.trim(),
        aliases_th: aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
        expected_group: expectedGroup.trim() || null,
        polarity,
      });
      onCreated(field);
    } catch (err) {
      setError(err.message || "สร้าง field ใหม่ไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = key.trim() && !submitting;

  return (
    <Modal title="สร้าง field กลางใหม่" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        {error && (
          <div className="banner banner-error" role="alert">
            {error}
          </div>
        )}

        <label className="field-label" htmlFor="new-field-key">
          key (snake_case)
        </label>
        <input
          id="new-field-key"
          className="select"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="เช่น special_allowance"
          disabled={submitting}
        />
        <p className="input-hint">ใช้ตัวพิมพ์เล็ก a–z, ตัวเลข และ _ เท่านั้น</p>

        <div style={{ height: 16 }} />

        <label className="field-label" htmlFor="new-field-aliases">
          ชื่อภาษาไทย (คั่นด้วยเครื่องหมายจุลภาค)
        </label>
        <input
          id="new-field-aliases"
          className="select"
          value={aliases}
          onChange={(e) => setAliases(e.target.value)}
          placeholder="เช่น เบี้ยพิเศษ, ค่าพิเศษ"
          disabled={submitting}
        />

        <div style={{ height: 16 }} />

        <label className="field-label" htmlFor="new-field-group">
          กลุ่มคอลัมน์ (expected_group) — ไม่บังคับ
        </label>
        <input
          id="new-field-group"
          className="select"
          value={expectedGroup}
          onChange={(e) => setExpectedGroup(e.target.value)}
          disabled={submitting}
        />

        <div style={{ height: 16 }} />

        <label className="field-label" htmlFor="new-field-polarity">
          ประเภท (polarity)
        </label>
        <select
          id="new-field-polarity"
          className="select"
          value={polarity}
          onChange={(e) => setPolarity(e.target.value)}
          disabled={submitting}
        >
          <option value="income">รายรับ (income)</option>
          <option value="deduction">รายหัก (deduction)</option>
        </select>

        <div className="actions">
          <button type="submit" className="btn btn-primary btn-block" disabled={!canSubmit}>
            {submitting ? (
              <>
                <span className="spinner" /> กำลังสร้าง…
              </>
            ) : (
              "สร้าง field"
            )}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>
            ยกเลิก
          </button>
        </div>
      </form>
    </Modal>
  );
}
