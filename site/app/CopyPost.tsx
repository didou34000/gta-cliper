"use client";
import { useState } from "react";
export default function CopyPost({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className="btn ghost" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); }
      catch { window.prompt("Copie ce texte :", text); }
    }}>{done ? "Copié" : "Copier titre + description + hashtags"}</button>
  );
}
