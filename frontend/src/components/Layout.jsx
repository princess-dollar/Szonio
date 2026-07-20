// หน้าหลัก -> calculate flow, จัดการบริษัท -> manage page (F4, now live).
const NAV_ITEMS = [
  { key: "home", label: "หน้าหลัก", page: "calculate" },
  { key: "companies", label: "จัดการบริษัท", page: "manage" },
];

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
            {NAV_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={`nav-link${page === item.page ? " active" : ""}`}
                aria-current={page === item.page ? "page" : undefined}
                onClick={() => onNavigate && onNavigate(item.page)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="nav-spacer" />
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
