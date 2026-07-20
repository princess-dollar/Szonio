import { useMemo, useState } from "react";
import Modal from "./Modal.jsx";

export default function FieldPickerModal({
  canonicalFields,
  usedFields,
  onPick,
  onClose,
  onCreateFieldClick,
}) {
  const [query, setQuery] = useState("");

  const available = useMemo(() => {
    const q = query.trim().toLowerCase();
    return canonicalFields
      .filter((f) => !usedFields.has(f.key))
      .filter((f) => {
        if (!q) return true;
        // Search the Thai names the admin actually sees, not the internal key.
        return (f.aliases_th || []).some((a) => a.toLowerCase().includes(q));
      });
  }, [canonicalFields, usedFields, query]);

  return (
    <Modal title="เพิ่มส่วนประกอบ" onClose={onClose}>
      <input
        className="select"
        type="search"
        placeholder="ค้นหา field…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="ค้นหา field"
        autoFocus
      />

      <button className="picker-create" onClick={onCreateFieldClick}>
        + เพิ่มรายการเงินใหม่
      </button>

      <div className="picker-list">
        {available.length === 0 ? (
          <div className="center-state">ไม่มี field ที่เพิ่มได้ (ใช้ครบแล้วหรือไม่ตรงคำค้นหา)</div>
        ) : (
          available.map((f) => (
            <button key={f.key} className="picker-item" onClick={() => onPick(f.key)}>
              <span className="picker-item-main">
                <span className="picker-item-thai">{(f.aliases_th && f.aliases_th[0]) || f.key}</span>
                {f.aliases_th && f.aliases_th.length > 1 && (
                  <span className="picker-item-key">{f.aliases_th.slice(1).join(", ")}</span>
                )}
              </span>
              <span className={`polarity-tag ${f.polarity}`}>
                {f.polarity === "income" ? "รายรับ" : "รายหัก"}
              </span>
            </button>
          ))
        )}
      </div>
    </Modal>
  );
}
