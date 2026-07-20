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
}) {
  const [previewValues, setPreviewValues] = useState({});

  const components = config.components;
  const hasSalary = components.some((c) => c.field === LOCKED_FIELD);
  const { base, contribution } = computePreview(components, previewValues);

  return (
    <section className="editor card">
      <div className="editor-head">
        <div>
          <h2>
            {config.display_name}{" "}
            <span className="version-badge">v{config.version}</span>
          </h2>
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
