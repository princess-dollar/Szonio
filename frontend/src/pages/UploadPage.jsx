import { useEffect, useState } from "react";
import Dropzone from "../components/Dropzone.jsx";
import { calculate, fetchCompanies } from "../api.js";

export default function UploadPage({ onCalculated }) {
  const [companies, setCompanies] = useState([]);
  const [companiesLoading, setCompaniesLoading] = useState(true);
  const [companiesError, setCompaniesError] = useState("");

  const [companyId, setCompanyId] = useState("");
  const [file, setFile] = useState(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [review, setReview] = useState(null);

  async function loadCompanies() {
    setCompaniesLoading(true);
    setCompaniesError("");
    try {
      const list = await fetchCompanies();
      setCompanies(list);
    } catch (err) {
      setCompaniesError(err.message || "โหลดรายชื่อบริษัทไม่สำเร็จ");
    } finally {
      setCompaniesLoading(false);
    }
  }

  useEffect(() => {
    loadCompanies();
  }, []);

  function resetAll() {
    setCompanyId("");
    setFile(null);
    setSubmitError("");
    setReview(null);
  }

  async function handleSubmit() {
    if (!companyId || !file || submitting) return;
    setSubmitting(true);
    setSubmitError("");
    setReview(null);
    try {
      const result = await calculate(file, companyId);
      if (result.status === "needs_review") {
        setReview(result.report_th || "ต้องตรวจสอบการแมปคอลัมน์ก่อนคำนวณ");
      } else {
        onCalculated(result, file.name);
      }
    } catch (err) {
      setSubmitError(err.message || "เกิดข้อผิดพลาดในการประมวลผล");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = Boolean(companyId) && Boolean(file) && !submitting;

  if (review) {
    return (
      <>
        <div className="page-head">
          <h1>ต้องตรวจสอบก่อนคำนวณ</h1>
          <p>ระบบไม่สามารถยืนยันการแมปคอลัมน์ได้อย่างมั่นใจ กรุณาตรวจสอบตามรายละเอียดด้านล่าง</p>
        </div>
        <div className="card review">
          <div className="banner banner-info" role="status">
            ยังไม่มีการคำนวณหรือสร้างไฟล์ผลลัพธ์ — แก้ไขไฟล์ Excel หรือการตั้งค่าแล้วลองใหม่อีกครั้ง
          </div>
          <pre>{review}</pre>
          <div className="actions">
            <button className="btn btn-primary" onClick={() => setReview(null)}>
              ← กลับไปแก้ไขและลองใหม่
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <h1>คำนวณค่าประกันสังคม (SSO)</h1>
        <p>เลือกบริษัทและอัปโหลดไฟล์ Excel เงินเดือน ระบบจะคำนวณเงินสมทบให้อัตโนมัติ</p>
      </div>

      <div className="card">
        {submitError && (
          <div className="banner banner-error" role="alert">
            {submitError}
          </div>
        )}

        <label className="field-label" htmlFor="company-select">
          เลือกบริษัท
        </label>

        {companiesLoading ? (
          <div className="center-state" aria-live="polite">
            <span className="spinner spinner-dark" /> กำลังโหลดรายชื่อบริษัท…
          </div>
        ) : companiesError ? (
          <div className="banner banner-error" role="alert">
            {companiesError}{" "}
            <button className="link" onClick={loadCompanies} style={{ marginLeft: 8 }}>
              ลองอีกครั้ง
            </button>
          </div>
        ) : (
          <select
            id="company-select"
            className="select"
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value)}
            disabled={submitting}
          >
            <option value="">— กรุณาเลือกบริษัท —</option>
            {companies.map((c) => (
              <option key={c.company_id} value={c.company_id}>
                {c.display_name}
              </option>
            ))}
          </select>
        )}

        <div style={{ height: 20 }} />

        <label className="field-label">ไฟล์ Excel เงินเดือน</label>
        <Dropzone
          file={file}
          onSelect={setFile}
          onRemove={() => setFile(null)}
          disabled={submitting}
        />

        <div className="actions">
          <button className="btn btn-primary btn-block" onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? (
              <>
                <span className="spinner" /> กำลังคำนวณ…
              </>
            ) : (
              "ยืนยัน"
            )}
          </button>
          <button className="btn btn-ghost" onClick={resetAll} disabled={submitting}>
            ล้างค่า
          </button>
        </div>

        {submitting && (
          <p className="dropzone-hint" style={{ textAlign: "center", marginTop: 14 }}>
            การคำนวณอาจใช้เวลาสักครู่ เนื่องจากระบบกำลังวิเคราะห์คอลัมน์ในไฟล์ของคุณ
          </p>
        )}
      </div>
    </>
  );
}
