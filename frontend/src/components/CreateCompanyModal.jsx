import { useState } from "react";
import Modal from "./Modal.jsx";
import { createCompany } from "../api.js";

// New companies start with the mandatory salary_per_period component so the
// created config is valid on the server (which requires exactly one).
const INITIAL_COMPONENTS = [{ field: "salary_per_period", sign: "+", required: true }];

export default function CreateCompanyModal({ onClose, onCreated }) {
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      // company_id is generated server-side; we only send the Thai name.
      const config = await createCompany({
        display_name: displayName.trim(),
        components: INITIAL_COMPONENTS,
      });
      onCreated(config);
    } catch (err) {
      setError(err.message || "สร้างบริษัทไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = displayName.trim() && !submitting;

  return (
    <Modal title="เพิ่มบริษัทใหม่" onClose={onClose}>
      <form onSubmit={handleSubmit}>
        {error && (
          <div className="banner banner-error" role="alert">
            {error}
          </div>
        )}

        <label className="field-label" htmlFor="new-company-name">
          ชื่อบริษัท
        </label>
        <input
          id="new-company-name"
          className="select"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="เช่น บริษัท เอซีเอ็ม จำกัด"
          disabled={submitting}
          autoFocus
        />

        <div className="actions">
          <button type="submit" className="btn btn-primary btn-block" disabled={!canSubmit}>
            {submitting ? (
              <>
                <span className="spinner" /> กำลังสร้าง…
              </>
            ) : (
              "สร้างบริษัท"
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
