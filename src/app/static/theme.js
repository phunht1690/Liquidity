"use strict";
(() => {
  const root = document.documentElement;
  const key = "lopm:theme";
  const system = window.matchMedia("(prefers-color-scheme: light)");
  let explicit = false;
  let mode = system.matches ? "light" : "dark";
  try {
    const saved = localStorage.getItem(key);
    if (saved === "light" || saved === "dark") { mode = saved; explicit = true; }
  } catch {}
  function apply(next) {
    mode = next;
    root.dataset.theme = next;
    root.classList.toggle("dark", next === "dark");
    root.style.colorScheme = next;
    const meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.content = next;
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      const label = next === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối";
      button.setAttribute("aria-label", label);
      button.title = label;
      button.querySelector("[data-theme-label]").textContent = next === "dark" ? "Sáng" : "Tối";
    });
  }
  apply(mode);
  document.addEventListener("DOMContentLoaded", () => {
    apply(mode);
    document.querySelectorAll("[data-theme-toggle]").forEach(button => {
      button.addEventListener("click", () => {
        explicit = true;
        apply(mode === "dark" ? "light" : "dark");
        try { localStorage.setItem(key, mode); } catch {}
      });
    });
  });
  system.addEventListener("change", event => { if (!explicit) apply(event.matches ? "light" : "dark"); });
  window.addEventListener("storage", event => {
    if (event.key !== key) return;
    explicit = event.newValue === "light" || event.newValue === "dark";
    apply(explicit ? event.newValue : system.matches ? "light" : "dark");
  });
})();
