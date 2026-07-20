import { useState } from "react";
import { downloadResult } from "../api.js";
import { formatMoney } from "../format.js";

export default function ResultPage({ result, fileName, onBack }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");

  const { summary, employees, download_token: token } = result;
  const company = summary.company;
  const downloadName = `${fileName ? fileName.replace(/\.(xlsx|xls)$/i, "") : "result"}_sso_result.xlsx`;

  async function handleDownload() {
    if (downloading) return;
    setDownloading(true);
    setDownloadError("");
    try {
      await downloadResult(token, downloadName);
    } catch (err) {
      setDownloadError(err.message || "ดาวน์โหลดไม่สำเร็จ");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <div className="card">
        <div className="result-head">
          <div>
            <h1>{company.display_name}</h1>
            <div className="result-meta">
              พนักงาน {summary.employee_count.toLocaleString("th-TH")} คน
              {fileName ? ` · ไฟล์: ${fileName}` : ""}
            </div>
          </div>
          <span className="badge-success">✓ คำนวณสำเร็จ</span>
        </div>

        <div className="summary-grid">
          <div className="summary-card">
            <div className="label">รวม Base SSO</div>
            <div className="value">
              {formatMoney(summary.total_base)}
              <span className="unit">บาท</span>
            </div>
          </div>
          <div className="summary-card">
            <div className="label">รวม SSO (เงินสมทบ)</div>
            <div className="value">
              {formatMoney(summary.total_contribution)}
              <span className="unit">บาท</span>
            </div>
          </div>
        </div>

        {downloadError && (
          <div className="banner banner-error" role="alert">
            {downloadError}
          </div>
        )}

        <div className="actions" style={{ marginTop: 0 }}>
          <button className="btn btn-primary" onClick={handleDownload} disabled={downloading}>
            {downloading ? (
              <>
                <span className="spinner" /> กำลังดาวน์โหลด…
              </>
            ) : (
              "⬇ ดาวน์โหลดผลลัพธ์ (.xlsx)"
            )}
          </button>
          <button className="btn btn-ghost" onClick={onBack}>
            คำนวณใหม่
          </button>
          <button className="btn btn-ghost" onClick={onBack}>
            กลับหน้าหลัก
          </button>
        </div>
      </div>

      <div className="card">
        <label className="field-label">รายละเอียดรายพนักงาน</label>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>รหัสพนักงาน</th>
                <th>ชื่อพนักงาน</th>
                <th className="num">Base SSO</th>
                <th className="num">SSO</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e, idx) => (
                <tr key={`${e.employee_id}-${idx}`}>
                  <td>{e.employee_id}</td>
                  <td>{e.employee_name ? e.employee_name : <span className="muted">—</span>}</td>
                  <td className="num">{formatMoney(e.base)}</td>
                  <td className="num">{formatMoney(e.contribution)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>รวมทั้งหมด ({summary.employee_count.toLocaleString("th-TH")} คน)</td>
                <td />
                <td className="num">{formatMoney(summary.total_base)}</td>
                <td className="num">{formatMoney(summary.total_contribution)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </>
  );
}
