import { useState } from "react";
import Layout from "./components/Layout.jsx";
import CalculateFlow from "./pages/CalculateFlow.jsx";
import ManagePage from "./pages/ManagePage.jsx";

export default function App() {
  // Lightweight view-state routing (no react-router). See F4 notes: only two
  // real top-level areas (calculate flow, manage), so a page switch keeps the
  // build dependency-free and matches the pattern already used in F3.
  const [page, setPage] = useState("calculate");

  function navigate(next) {
    setPage(next);
    window.scrollTo({ top: 0 });
  }

  return (
    <Layout page={page} onNavigate={navigate}>
      {page === "manage" ? <ManagePage /> : <CalculateFlow />}
    </Layout>
  );
}
