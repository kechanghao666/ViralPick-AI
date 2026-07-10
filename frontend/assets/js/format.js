const numberFormatter = new Intl.NumberFormat("zh-CN");
const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});

export function number(value, digits = 0) {
  const numeric = Number(value) || 0;
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numeric);
}

export function money(value) {
  return moneyFormatter.format(Number(value) || 0);
}

export function percent(value, digits = 1) {
  return `${((Number(value) || 0) * 100).toFixed(digits)}%`;
}

export function compact(value) {
  const numeric = Number(value) || 0;
  if (Math.abs(numeric) >= 100000000) {
    return `${(numeric / 100000000).toFixed(1)}亿`;
  }
  if (Math.abs(numeric) >= 10000) {
    return `${(numeric / 10000).toFixed(1)}万`;
  }
  return numberFormatter.format(Math.round(numeric));
}

export function signedPercent(value, digits = 1) {
  const numeric = Number(value) || 0;
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${(numeric * 100).toFixed(digits)}%`;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
