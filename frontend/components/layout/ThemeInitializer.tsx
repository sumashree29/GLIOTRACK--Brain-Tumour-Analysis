"use client";

import { useEffect } from "react";

export default function ThemeInitializer() {
  useEffect(() => {
    const saved = localStorage.getItem("gliotrack-theme") ?? "dark";
    document.documentElement.setAttribute("data-theme", saved);
  }, []);

  return null;
}
