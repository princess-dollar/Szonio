import { useState } from "react";
import UploadPage from "./UploadPage.jsx";
import ResultPage from "./ResultPage.jsx";

// The upload -> result flow, kept as its own internal two-view state so the
// top-level page switch in App only deals with "calculate" vs "manage".
export default function CalculateFlow() {
  const [view, setView] = useState("upload");
  const [result, setResult] = useState(null);
  const [fileName, setFileName] = useState("");

  function handleCalculated(data, name) {
    setResult(data);
    setFileName(name);
    setView("result");
    window.scrollTo({ top: 0 });
  }

  function backToUpload() {
    setResult(null);
    setFileName("");
    setView("upload");
    window.scrollTo({ top: 0 });
  }

  return view === "result" && result ? (
    <ResultPage result={result} fileName={fileName} onBack={backToUpload} />
  ) : (
    <UploadPage onCalculated={handleCalculated} />
  );
}
