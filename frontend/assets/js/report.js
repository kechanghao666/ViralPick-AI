import { escapeHtml } from "./format.js";

export function markdownToHtml(markdown = "") {
  return escapeHtml(markdown)
    .split("\n")
    .map((line) => {
      if (line.startsWith("# ")) return `<h2>${line.slice(2)}</h2>`;
      if (line.startsWith("## ")) return `<h3>${line.slice(3)}</h3>`;
      if (!line.trim()) return "";
      return `<p>${line}</p>`;
    })
    .join("");
}
