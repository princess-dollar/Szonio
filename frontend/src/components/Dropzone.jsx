import { useRef, useState } from "react";
import { formatFileSize } from "../format.js";

const ACCEPT = ".xlsx,.xls";

function hasValidExtension(name) {
  const lower = name.toLowerCase();
  return lower.endsWith(".xlsx") || lower.endsWith(".xls");
}

export default function Dropzone({ file, onSelect, onRemove, disabled }) {
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState("");
  const inputRef = useRef(null);

  function handleFiles(fileList) {
    setLocalError("");
    const picked = fileList && fileList[0];
    if (!picked) return;
    if (!hasValidExtension(picked.name)) {
      setLocalError("รองรับเฉพาะไฟล์ .xlsx หรือ .xls เท่านั้น");
      return;
    }
    onSelect(picked);
  }

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    handleFiles(event.dataTransfer.files);
  }

  if (file) {
    return (
      <div className="file-chip">
        <div className="file-chip-icon" aria-hidden="true">📄</div>
        <div className="file-chip-meta">
          <div className="file-chip-name">{file.name}</div>
          <div className="file-chip-size">{formatFileSize(file.size)}</div>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onRemove}
          disabled={disabled}
          aria-label="ลบไฟล์ที่เลือก"
        >
          ✕
        </button>
      </div>
    );
  }

  return (
    <div>
      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !disabled) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="เลือกหรือวางไฟล์ Excel ที่นี่"
      >
        <div className="dropzone-icon" aria-hidden="true">⬆️</div>
        <div>
          ลากไฟล์ Excel มาวางที่นี่ หรือ{" "}
          <button
            type="button"
            className="link"
            onClick={(e) => {
              e.stopPropagation();
              inputRef.current?.click();
            }}
            disabled={disabled}
          >
            เลือกไฟล์
          </button>
        </div>
        <div className="dropzone-hint">รองรับไฟล์ .xlsx และ .xls</div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {localError && (
        <div className="banner banner-error" role="alert" style={{ marginTop: 12, marginBottom: 0 }}>
          {localError}
        </div>
      )}
    </div>
  );
}
