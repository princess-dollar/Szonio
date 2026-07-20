import { useMemo, useState } from "react";

export default function CompanyList({
  companies,
  loading,
  error,
  selectedId,
  onSelect,
  onReload,
  onCreateClick,
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return companies;
    // Search by the Thai name only — company_id is an internal id admins never see.
    return companies.filter((c) => c.display_name.toLowerCase().includes(q));
  }, [companies, query]);

  return (
    <aside className="company-list card">
      <div className="company-list-head">
        <h2>บริษัท</h2>
        <button className="btn btn-primary btn-sm" onClick={onCreateClick}>
          + เพิ่มบริษัทใหม่
        </button>
      </div>

      <input
        className="select"
        type="search"
        placeholder="ค้นหาบริษัท…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="ค้นหาบริษัท"
      />

      <div className="company-list-body">
        {loading ? (
          <div className="center-state">
            <span className="spinner spinner-dark" /> กำลังโหลด…
          </div>
        ) : error ? (
          <div className="banner banner-error" role="alert">
            {error}{" "}
            <button className="link" onClick={onReload}>
              ลองอีกครั้ง
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="center-state">ไม่พบบริษัทที่ตรงกับคำค้นหา</div>
        ) : (
          <ul className="company-items">
            {filtered.map((c) => (
              <li key={c.company_id}>
                <button
                  className={`company-item${c.company_id === selectedId ? " active" : ""}`}
                  onClick={() => onSelect(c.company_id)}
                  aria-current={c.company_id === selectedId ? "true" : undefined}
                >
                  <span className="company-item-name">{c.display_name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
