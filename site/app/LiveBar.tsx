"use client";
// Suivi en direct d'un passage, visible sur toutes les pages.
// Interroge /api/live toutes les 4 s pendant un passage (GitHub + statut du bot),
// toutes les 60 s sinon, et recharge la page une seule fois quand le passage se termine.
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Live } from "./api/live/route";

const STAGES = ["Envoyé", "Démarrage", "Recherche", "Transcription", "Titre", "Montage", "Sur le site"];
const NODE_STAGE: Record<string, number> = { twitch: 2, scoring: 2, transcription: 3, titre: 4, render: 5, site: 6 };

function dur(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")}`;
}
function hm(iso: string) {
  return new Date(iso).toLocaleTimeString("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function LiveBar({ initial, sent, full }: { initial: Live; sent?: number; full?: boolean }) {
  const router = useRouter();
  const [live, setLive] = useState<Live>(initial);
  const [now, setNow] = useState(() => Date.now());
  const [open, setOpen] = useState(!!full);
  const wasActive = useRef(false);

  const run = live.run;
  const created = run ? +new Date(run.created_at) : 0;
  const waiting = !!sent && Date.now() - sent < 3 * 60_000 && (!run || created < sent - 15_000);
  const active = waiting || (!!run && run.status !== "completed");

  useEffect(() => {
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (!document.hidden) {
        try {
          const r = await fetch("/api/live", { cache: "no-store" });
          if (r.ok && !stop) setLive(await r.json());
        } catch { /* réseau coupé : on réessaie au prochain tour */ }
      }
      if (!stop) t = setTimeout(tick, active ? 4000 : 60000);
    };
    t = setTimeout(tick, active ? 2000 : 60000);
    return () => { stop = true; clearTimeout(t); };
  }, [active]);

  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(i);
  }, []);

  useEffect(() => {
    if (wasActive.current && !active) router.refresh(); // fin du passage : nouveaux clips à l'écran
    wasActive.current = active;
  }, [active, router]);

  // Statut du bot appartenant à ce passage (pas à un ancien).
  const beat = live.beat && run && +new Date(live.beat.ts) >= created - 60_000 ? live.beat : null;
  const label = run?.kind === "youtube" ? "Vidéo YouTube" : "Passage Twitch";

  let stage = 0, tone = "run", title = "", detail = "";
  if (waiting) {
    stage = 0; title = "Demande envoyée";
    detail = `GitHub prépare une machine pour le bot (en général 20 à 60 s) · envoyé il y a ${dur(now - sent!)}`;
  } else if (!run) {
    if (!full) return null;
    tone = "idle"; title = "Aucun passage récent"; detail = "Lance-en un depuis Programmation.";
  } else if (run.status === "queued") {
    stage = 1; title = `${label} en file d'attente`;
    detail = "GitHub va démarrer la machine. Si un autre passage tourne, celui-ci attend qu'il finisse.";
  } else if (run.status === "in_progress") {
    const working = run.mainStep?.status === "in_progress";
    stage = working ? Math.max(2, NODE_STAGE[beat?.node ?? ""] ?? 2) : 1;
    title = working ? `${label} en cours` : `${label} : démarrage`;
    detail = working
      ? (beat?.events?.at(-1)?.text || beat?.message || "Le bot commence…")
      : `Installation de la machine : ${run.step ?? "préparation"} (1 à 2 min)`;
  } else {
    const ok = run.conclusion === "success" && beat?.status !== "error";
    const ago = now - +new Date(run.updated_at);
    if (!full && ago > 20 * 60_000) return null; // vieux résultat : on n'encombre pas les autres pages
    tone = ok ? "ok" : run.conclusion === "cancelled" ? "idle" : "ko";
    stage = STAGES.length;
    const n = beat?.stats?.clips_produits;
    title = ok ? `${label} terminé` : run.conclusion === "cancelled" ? `${label} annulé` : `${label} en échec`;
    detail = ok
      ? `${n != null ? `${n} clip${n > 1 ? "s" : ""} produit${n > 1 ? "s" : ""}` : "Fini"} · en ${dur(+new Date(run.updated_at) - created)} · ${hm(run.updated_at)}`
      : (beat?.status === "error" ? beat.message : null) || beat?.events?.filter((e) => e.level === "error").at(-1)?.text
        || `Arrêté pendant « ${run.steps?.find((s) => s.conclusion === "failure")?.name ?? "?"} ». Le détail est sur GitHub.`;
  }

  const events = beat?.events?.slice(full ? -12 : -6).reverse() ?? [];
  return (
    <section className={`live live-${tone}`} aria-live="polite">
      <div className="live-head">
        <span className="live-dot" aria-hidden="true" />
        <div className="live-txt">
          <b>{title}</b>
          <span>{detail}</span>
        </div>
        <div className="live-side">
          {active && run && <span className="live-time mono">{dur(now - created)}</span>}
          {run && <a href={run.url} target="_blank" rel="noreferrer" className="link small">GitHub</a>}
          {tone === "ok" && <a href="/?v=valider" className="btn-sm">Voir les clips</a>}
          {events.length > 0 && <button type="button" className="link small live-more" onClick={() => setOpen(!open)}>{open ? "Masquer" : "Détails"}</button>}
        </div>
      </div>
      {(active || tone !== "idle") && run !== null && (
        <ol className="live-steps" aria-label="Étapes">
          {STAGES.map((s, i) => (
            <li key={s} className={i < stage ? "done" : i === stage && active ? "now" : ""}>{s}</li>
          ))}
        </ol>
      )}
      {open && events.length > 0 && (
        <ol className="live-events">
          {events.map((e, i) => (
            <li key={i} className={`ev-${e.level}`}><time className="mono">{hm(e.ts)}</time>{e.streamer && <b>{e.streamer}</b>}<span>{e.text}</span></li>
          ))}
        </ol>
      )}
    </section>
  );
}
