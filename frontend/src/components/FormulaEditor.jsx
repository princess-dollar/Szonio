import { useState } from "react";
import {
  computePreview,
  fieldGroup,
  fieldLabel,
  formatNumber,
  formulaExpression,
} from "../manage.js";

const LOCKED_FIELD = "salary_per_period";

export default function FormulaEditor({
  config,
  fieldsByKey,
  dirty,
  saving,
  saveError,
  saveOk,
  onChangeComponent,
  onRemoveComponent,
  onAddComponentClick,
  onSave,
  onReset,
  onRename,
}) {
  const [previewValues, setPreviewValues] = useState({});

  // Inline rename (display_name only). Independent of formula editing state —
  // it never touches components, so unsaved formula edits are preserved.
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameError, setRenameError] = useState("");

  const components = config.components;
  const hasSalary = components.some((c) => c.field === LOCKED_FIELD);
  const { base, contribution } = computePreview(components, previewValues);

  function startRename() {
    setNameDraft(config.display_name);
    setRenameError("");
    setEditingName(true);
  }

  function cancelRename() {
    setEditingName(false);
    setRenameError("");
  }

  async function submitRename() {
    const trimmed = nameDraft.trim();
    if (!trimmed) {
      setRenameError("กรุณาระบุชื่อบริษัท"); // light client guard; API is authoritative
      return;
    }
    setRenaming(true);
    setRenameError("");
    try {
      await onRename(trimmed);
      setEditingName(false); // keep edit mode open on failure so they can fix it
    } catch (err) {
      setRenameError(err.message || "เปลี่ยนชื่อบริษัทไม่สำเร็จ");
    } finally {
      setRenaming(false);
    }
  }

  return (
    <section className="editor card">
      <div className="editor-head">
        <div className="editor-title">
          {editingName ? (
            <div className="name-edit">
              <input
                className="select name-input"
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    submitRename();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    cancelRename();
                  }
                }}
                disabled={renaming}
                autoFocus
                aria-label="ชื่อบริษัท"
              />
              <button
                className="icon-button ok"
                onClick={submitRename}
                disabled={renaming}
                title="บันทึกชื่อ"
                aria-label="บันทึกชื่อ"
              >
                {renaming ? <span className="spinner spinner-dark" /> : "✓"}
              </button>
              <button
                className="icon-button"
                onClick={cancelRename}
                disabled={renaming}
                title="ยกเลิก"
                aria-label="ยกเลิกการเปลี่ยนชื่อ"
              >
                ✕
              </button>
              <span className="version-badge">v{config.version}</span>
            </div>
          ) : (
            <h2>
              {config.display_name}{" "}
              <button
                className="icon-button edit-name-btn"
                onClick={startRename}
                disabled={saving}
                title="เปลี่ยนชื่อบริษัท"
                aria-label="เปลี่ยนชื่อบริษัท"
              >
                ✎
              </button>{" "}
              <span className="version-badge">v{config.version}</span>
            </h2>
          )}
          {renameError && (
            <div className="banner banner-error rename-error" role="alert">
              {renameError}
            </div>
          )}
        </div>
        <div className="editor-actions">
          {dirty && <span className="dirty-hint">● แก้ไขยังไม่บันทึก</span>}
          <button className="btn btn-ghost" onClick={onReset} disabled={saving || !dirty}>
            คืนค่าเดิม
          </button>
          <button className="btn btn-primary" onClick={onSave} disabled={saving || !hasSalary}>
            {saving ? (
              <>
                <span className="spinner" /> กำลังบันทึก…
              </>
            ) : (
              "บันทึกสูตร"
            )}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="banner banner-error" role="alert">
          {saveError}
        </div>
      )}
      {saveOk && !dirty && (
        <div className="banner banner-success" role="status">
          บันทึกสูตรเรียบร้อยแล้ว (เวอร์ชัน {config.version})
        </div>
      )}
      {!hasSalary && (
        <div className="banner banner-error" role="alert">
          สูตรต้องมี salary_per_period อย่างน้อยหนึ่งรายการจึงจะบันทึกได้
        </div>
      )}

      <label className="field-label">ส่วนประกอบของสูตร</label>
      <div className="component-rows">
        {components.map((c, index) => {
          const locked = c.field === LOCKED_FIELD;
          const group = fieldGroup(c.field, fieldsByKey);
          return (
            <div className="component-row" key={c.field}>
              <div className="component-name">
                <span className="component-thai">{fieldLabel(c.field, fieldsByKey)}</span>
                {/* Group only — the field key is an internal id and is never shown. */}
                {group && <span className="component-meta">{group}</span>}
              </div>

              <div className="sign-toggle" role="group" aria-label="เครื่องหมาย">
                <button
                  className={`sign-btn${c.sign === "+" ? " active" : ""}`}
                  onClick={() => onChangeComponent(index, { sign: "+" })}
                  disabled={saving}
                  aria-pressed={c.sign === "+"}
                >
                  +
                </button>
                <button
                  className={`sign-btn${c.sign === "-" ? " active minus" : ""}`}
                  onClick={() => onChangeComponent(index, { sign: "-" })}
                  disabled={saving}
                  aria-pressed={c.sign === "-"}
                >
                  −
                </button>
              </div>

              <label className={`switch${locked ? " switch-locked" : ""}`}>
                <input
                  type="checkbox"
                  checked={c.required}
                  disabled={locked || saving}
                  onChange={(e) => onChangeComponent(index, { required: e.target.checked })}
                />
                <span>จำเป็น</span>
              </label>

              <button
                className="icon-button"
                onClick={() => onRemoveComponent(index)}
                disabled={locked || saving}
                title={locked ? "salary_per_period ลบไม่ได้" : "ลบส่วนประกอบ"}
                aria-label="ลบส่วนประกอบ"
              >
                {locked ? "🔒" : "✕"}
              </button>
            </div>
          );
        })}
      </div>

      <button className="btn btn-ghost btn-add" onClick={onAddComponentClick} disabled={saving}>
        + เพิ่มส่วนประกอบ
      </button>

      <div className="formula-preview">
        <label className="field-label">ตัวอย่างสูตร</label>
        <div className="formula-expression">
          <span className="formula-base">ฐาน =</span> {formulaExpression(components, fieldsByKey)}
        </div>
      </div>

      <div className="calc-preview">
        <label className="field-label">ตัวอย่างการคำนวณ</label>
        <div className="banner banner-info">
          ตัวอย่างประมาณการ — เลขจริงคำนวณด้วยระบบตอนอัปโหลดไฟล์เท่านั้น
        </div>
        <div className="preview-inputs">
          {components.map((c) => (
            <div className="preview-input" key={c.field}>
              <label htmlFor={`pv-${c.field}`}>
                <span className="sign-tag">{c.sign}</span>{" "}
                {fieldLabel(c.field, fieldsByKey)}
              </label>
              <input
                id={`pv-${c.field}`}
                type="number"
                inputMode="decimal"
                className="select"
                value={previewValues[c.field] ?? ""}
                placeholder="0"
                onChange={(e) =>
                  setPreviewValues((v) => ({ ...v, [c.field]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>
        <div className="preview-result">
          <div className="preview-stat">
            <span className="label">ฐาน (ประมาณการ)</span>
            <span className="value">{formatNumber(base)}</span>
          </div>
          <div className="preview-stat">
            <span className="label">เงินสมทบ (ประมาณการ)</span>
            <span className="value">{formatNumber(contribution)}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
