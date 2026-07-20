import { useEffect, useRef, useState } from "react";

// หน้าหลัก -> calculate flow, จัดการบริษัท -> manage page (F4, now live).
// ตั้งค่า stays disabled (out of scope). ประวัติการคำนวณ is dropped entirely.
const NAV_ITEMS = [
  { key: "home", label: "หน้าหลัก", page: "calculate" },
  { key: "companies", label: "จัดการบริษัท", page: "manage" },
  { key: "settings", label: "ตั้งค่า", page: null },
];

function AdminMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(event) {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  return (
    <div className="admin" ref={ref}>
      <button
        className="admin-button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="admin-avatar">A</span>
        <span>Admin</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="admin-menu" role="menu">
          <button role="menuitem" type="button">โปรไฟล์</button>
          <button role="menuitem" type="button">ออกจากระบบ</button>
        </div>
      )}
    </div>
  );
}

export default function Layout({ page = "calculate", onNavigate, children }) {
  return (
    <div className="app">
      <header className="topnav">
        <div className="topnav-inner">
          <div className="brand">
            <div className="brand-logo" aria-hidden="true">S</div>
            <div className="brand-text">
              <span className="brand-title">SSO Service</span>
              <span className="brand-sub">คำนวณค่า SSO อัตโนมัติ</span>
            </div>
          </div>

          <nav className="nav-links" aria-label="เมนูหลัก">
            {NAV_ITEMS.map((item) =>
              item.page ? (
                <button
                  key={item.key}
                  type="button"
                  className={`nav-link${page === item.page ? " active" : ""}`}
                  aria-current={page === item.page ? "page" : undefined}
                  onClick={() => onNavigate && onNavigate(item.page)}
                >
                  {item.label}
                </button>
              ) : (
                <span
                  key={item.key}
                  className="nav-link disabled"
                  title="อยู่ระหว่างการพัฒนา"
                  aria-disabled="true"
                >
                  {item.label}
                </span>
              )
            )}
          </nav>

          <div className="nav-spacer" />
          <AdminMenu />
        </div>
      </header>

      <main className="main">{children}</main>

      <footer className="footer">
        <span aria-hidden="true">🔒</span>
        ข้อมูลของคุณปลอดภัย ด้วยการเข้ารหัสระดับองค์กร
      </footer>
    </div>
  );
}
