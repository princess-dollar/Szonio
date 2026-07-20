// Helpers for the formula-management page.

// These MUST mirror sso_rule.json. This preview is a DESIGN ESTIMATE only —
// authoritative SSO numbers always come from the Python pipeline on upload.
export const PREVIEW_CEILING = 17500;
export const PREVIEW_RATE = 0.05;

export function fieldLabel(fieldKey, fieldsByKey) {
  const f = fieldsByKey[fieldKey];
  if (f && f.aliases_th && f.aliases_th.length > 0) return f.aliases_th[0];
  return fieldKey;
}

export function fieldGroup(fieldKey, fieldsByKey) {
  const f = fieldsByKey[fieldKey];
  return f ? f.expected_group : null;
}

export function formulaExpression(components, fieldsByKey) {
  if (!components.length) return "—";
  return components
    .map((c, idx) => {
      const name = fieldLabel(c.field, fieldsByKey);
      if (idx === 0) return c.sign === "-" ? `− ${name}` : name;
      return `${c.sign === "-" ? "−" : "+"} ${name}`;
    })
    .join("  ");
}

function round2HalfUp(value) {
  // Positive-only inputs here; Math.round rounds .5 up, matching ROUND_HALF_UP.
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

// Browser-side ESTIMATE: base = signed sum (negatives clamped to 0);
// contribution = min(base, ceiling) * rate, 2dp. Not the real calculation.
export function computePreview(components, values) {
  let base = 0;
  for (const c of components) {
    const raw = values[c.field];
    const num = raw === undefined || raw === "" ? 0 : parseFloat(raw);
    const amount = Number.isFinite(num) ? num : 0;
    base += c.sign === "-" ? -amount : amount;
  }
  base = Math.max(base, 0);
  const contribution = round2HalfUp(Math.min(base, PREVIEW_CEILING) * PREVIEW_RATE);
  return { base, contribution };
}

export function formatNumber(value) {
  return value.toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
