// Money values arrive from the API as decimal STRINGS. We never parseFloat
// them (that would risk precision loss); the original string stays the source
// of truth. These helpers only produce a display string.

export function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "-";
  const str = String(value);
  const negative = str.startsWith("-");
  const unsigned = negative ? str.slice(1) : str;

  const [intPartRaw, fracPartRaw = ""] = unsigned.split(".");
  const fracPart = (fracPartRaw + "00").slice(0, 2);
  const intPart = intPartRaw.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  return `${negative ? "-" : ""}${intPart}.${fracPart}`;
}

export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
