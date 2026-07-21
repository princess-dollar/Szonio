// Single place that knows the API base URL and the F2a contract. Components
// never hardcode the URL — it comes from VITE_API_BASE (see .env.example).

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readDetail(response, fallback) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    // non-JSON body; fall through to the generic message
  }
  return fallback;
}

export async function fetchCompanies() {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/companies`);
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบว่าระบบ API กำลังทำงานอยู่", 0);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response, "โหลดรายชื่อบริษัทไม่สำเร็จ"), response.status);
  }
  const body = await response.json();
  return body.companies || [];
}

// Returns the parsed body for both ok and needs_review (both are HTTP 200).
// Throws ApiError (with .status) for 400 / 413 / 502 / network failures.
export async function calculate(file, companyId) {
  const form = new FormData();
  form.append("file", file);
  form.append("company_id", companyId);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/calculate`, { method: "POST", body: form });
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่อีกครั้ง", 0);
  }

  if (!response.ok) {
    const fallbackByStatus = {
      400: "ไฟล์หรือข้อมูลไม่ถูกต้อง",
      413: "ไฟล์มีขนาดใหญ่เกินกำหนด",
      502: "ระบบเชื่อมต่อ LLM Gateway ไม่สำเร็จ กรุณาลองใหม่ภายหลัง",
    };
    const fallback = fallbackByStatus[response.status] || "เกิดข้อผิดพลาดในการประมวลผล";
    throw new ApiError(await readDetail(response, fallback), response.status);
  }

  return response.json();
}

// Single-use download. Fetches the file so a 404 (already downloaded / expired)
// can be surfaced as a friendly message instead of a broken navigation.
export async function downloadResult(token, filename) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/download/${token}`);
  } catch {
    throw new ApiError("ดาวน์โหลดไม่สำเร็จ กรุณาลองใหม่", 0);
  }
  if (response.status === 404) {
    throw new ApiError("ไฟล์นี้ถูกดาวน์โหลดไปแล้วหรือหมดอายุ กรุณาคำนวณใหม่เพื่อสร้างไฟล์อีกครั้ง", 404);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response, "ดาวน์โหลดไม่สำเร็จ"), response.status);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "sso_result.xlsx";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// --- F2b: config management -----------------------------------------------

async function sendJson(path, method, body, fallback) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่อีกครั้ง", 0);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response, fallback), response.status);
  }
  return response.json();
}

export async function getCompany(companyId) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/companies/${companyId}`);
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่อีกครั้ง", 0);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response, "โหลดสูตรบริษัทไม่สำเร็จ"), response.status);
  }
  return response.json();
}

export function saveCompany(companyId, { display_name, components }) {
  return sendJson(
    `/api/companies/${companyId}`,
    "PUT",
    { display_name, components },
    "บันทึกสูตรไม่สำเร็จ"
  );
}

// Rename edits display_name only (PATCH). Does not touch the formula or bump
// version. Returns the updated config (version unchanged).
export function renameCompany(companyId, displayName) {
  return sendJson(
    `/api/companies/${companyId}`,
    "PATCH",
    { display_name: displayName },
    "เปลี่ยนชื่อบริษัทไม่สำเร็จ"
  );
}

// No company_id: the server generates an opaque one and returns it. The UI
// uses the returned id only internally (selection/routing), never displays it.
export function createCompany({ display_name, components }) {
  return sendJson(
    "/api/companies",
    "POST",
    { display_name, components },
    "สร้างบริษัทไม่สำเร็จ"
  );
}

export async function fetchCanonicalFields() {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/canonical-fields`);
  } catch {
    throw new ApiError("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่อีกครั้ง", 0);
  }
  if (!response.ok) {
    throw new ApiError(await readDetail(response, "โหลดรายการ field ไม่สำเร็จ"), response.status);
  }
  const body = await response.json();
  return body.canonical_fields || [];
}

// No key: the server generates an opaque one. name_th_primary is the field's
// main Thai name and becomes aliases_th[0] (the label shown everywhere).
export async function createCanonicalField({
  name_th_primary,
  aliases_th,
  expected_group,
  polarity,
}) {
  const body = await sendJson(
    "/api/canonical-fields",
    "POST",
    { name_th_primary, aliases_th, expected_group, polarity },
    "เพิ่มรายการไม่สำเร็จ"
  );
  return body.canonical_field;
}
