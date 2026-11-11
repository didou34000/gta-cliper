"use client";
export default function AltTitles({ titles, inputId }: { titles: string[]; inputId: string }) {
  if (!titles?.length) return null;
  return (
    <div className="alts">
      {titles.map((t) => (
        <button key={t} type="button" onClick={() => {
          const el = document.getElementById(inputId) as HTMLInputElement | null;
          if (el) el.value = t;
        }}>{t}</button>
      ))}
    </div>
  );
}
