// Petits formats d'affichage partagés par les vues du tableau de bord.
const TZ = "Europe/Paris";

export function ago(iso?: string) {
  if (!iso) return "jamais";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `il y a ${h} h ${String(m % 60).padStart(2, "0")}`;
  return `il y a ${Math.floor(h / 24)} j`;
}

export function inFuture(iso?: string) {
  if (!iso) return "";
  const m = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  if (m <= 0) return "maintenant";
  if (m < 60) return `dans ${m} min`;
  const h = Math.floor(m / 60);
  return h < 48 ? `dans ${h} h ${String(m % 60).padStart(2, "0")}` : `dans ${Math.floor(h / 24)} j`;
}

export function fmtMin(n: number) {
  return n < 60 ? `${n} min` : n % 60 === 0 ? `${n / 60} h` : `${Math.floor(n / 60)} h ${n % 60}`;
}

export function fmtHours(h: number) {
  return h < 48 || h % 24 !== 0 ? `${h} dernières heures` : `${h / 24} derniers jours (${h} h)`;
}

export function fmtHoursShort(h?: number) {
  if (!h) return "";
  return h >= 48 && h % 24 === 0 ? `${h / 24} j` : `${h} h`;
}

/** 1 234 · 12,3 k · 1,2 M */
export function compact(n: number) {
  if (n < 10_000) return Math.round(n).toLocaleString("fr-FR");
  if (n < 1_000_000) return `${(n / 1000).toLocaleString("fr-FR", { maximumFractionDigits: n < 100_000 ? 1 : 0 })} k`;
  return `${(n / 1_000_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M`;
}

export function pct(n: number | null | undefined) {
  return n == null ? "—" : `${n.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
}

export function hhmm(iso: string) {
  return new Date(iso).toLocaleTimeString("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}

export function hhmmss(iso: string) {
  return new Date(iso).toLocaleTimeString("fr-FR", { timeZone: TZ });
}

export function dayTime(iso: string) {
  const d = new Date(iso);
  const day = d.toLocaleDateString("fr-FR", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
  return `${day} à ${hhmm(iso)}`;
}

export function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { timeZone: TZ, day: "numeric", month: "short" });
}

export function mb(bytes: number) {
  return `${(bytes / 1024 / 1024).toLocaleString("fr-FR", { maximumFractionDigits: bytes < 100 * 1024 * 1024 ? 1 : 0 })} Mo`;
}

export function euros(cents: number) {
  return cents < 100
    ? `${cents.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} centime${cents >= 2 ? "s" : ""}`
    : `${(cents / 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} €`;
}
