import { useState } from "react";
import Modal from "./Modal.jsx";
import { createCanonicalField } from "../api.js";

// polarity is income|deduction only — identity fields (employee_id/name) are
// system metadata and are never created through this UI (the API rejects them).
export default function CreateFieldModal({ onClose, onCreated }) {
  const [nameThPrimary, setNameThPrimary] = useState("");
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
      // key is generated server-side; we send only the Thai name(s).
      const field = await createCanonicalField({
        name_th_primary: nameThPrimary.trim(),
        aliases_th: aliases
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
        expected_group: expectedGroup.trim() || null,
        polarity,
      });
      onCreated(field);
    } catch (err) {
      setError(err.message || "เพิ่มรายการไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = nameThPrimary.trim() && !submitting;

  return (
    <Modal title="เพิ่มรายการเงินใหม่" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        {error && (
          <div className="banner banner-error" role="alert">
            {error}
          </div>
        )}

        <label className="field-label" htmlFor="new-field-name">
          ชื่อ (ภาษาไทย)
        </label>
        <input
          id="new-field-name"
          className="select"
          value={nameThPrimary}
          onChange={(e) => setNameThPrimary(e.target.value)}
          placeholder="เช่น ค่าครองชีพ"
          disabled={submitting}
          autoFocus
        />
        <p className="input-hint">ชื่อนี้จะแสดงทุกที่ในระบบ</p>

        <div style={{ height: 16 }} />

        <label className="field-label" htmlFor="new-field-aliases">
          ชื่ออื่นที่อาจเจอในไฟล์ Excel (ไม่บังคับ)
        </label>
        <input
          id="new-field-aliases"
          className="select"
          value={aliases}
          onChange={(e) => setAliases(e.target.value)}
          placeholder="เช่น ค่าพิเศษ, เงินพิเศษ"
          disabled={submitting}
        />
        <p className="input-hint">
          ถ้าบางบริษัทเรียกสิ่งนี้ด้วยชื่อต่างออกไป ใส่ไว้ที่นี่ (คั่นด้วยจุลภาค)
          ระบบจะจับคู่คอลัมน์ได้แม่นขึ้น
        </p>

        <div style={{ height: 16 }} />

        <label className="field-label" htmlFor="new-field-polarity">
          ประเภท
        </label>
        <select
          id="new-field-polarity"
          className="select"
          value={polarity}
          onChange={(e) => setPolarity(e.target.value)}
          disabled={submitting}
        >
          <option value="income">รายรับ (บวกเข้าฐาน)</option>
          <option value="deduction">รายหัก (ลบออกจากฐาน)</option>
        </select>

        <details className="advanced">
          <summary>ตัวเลือกขั้นสูง</summary>
          <div className="advanced-body">
            <label className="field-label" htmlFor="new-field-group">
              กลุ่มหัวตารางในไฟล์ (ไม่บังคับ)
            </label>
            <input
              id="new-field-group"
              className="select"
              value={expectedGroup}
              onChange={(e) => setExpectedGroup(e.target.value)}
              disabled={submitting}
            />
            <p className="input-hint">
              ใช้เมื่อมีคอลัมน์ชื่อคล้ายกันมาก เช่น แยก “ชดเชยวันลา” (รายรับ)
              ออกจาก “ชดเชยวันลา” ฝั่งหัก
            </p>
          </div>
        </details>

        <div className="actions">
          <button type="submit" className="btn btn-primary btn-block" disabled={!canSubmit}>
            {submitting ? (
              <>
                <span className="spinner" /> กำลังบันทึก…
              </>
            ) : (
              "เพิ่มรายการ"
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
