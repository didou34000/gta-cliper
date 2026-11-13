// Données communes à toutes les vues + petits composants d'affichage réutilisés.
import type { ReactNode } from "react";
import type { Clip, Heartbeat } from "@/lib/data";
import type { Schedule } from "@/lib/schedule";
import { BOT_START as BOT_START_ISO, type PostStats, type StatsResult } from "@/lib/stats";
import { compact, shortDate } from "@/lib/format";

export type BotStateKey = "never" | "offline" | "error" | "running" | "idle";

export type Ctx = {
  clips: Clip[];
  bytes: number;
  last: Heartbeat | null;
  state: { key: BotStateKey; label: string };
  schedule: Schedule;
  lastRun: string | null;
  nextRun: Date | null;
  stats: StatsResult;
  configured: boolean;
  counts: { pending: number; approved: number; posted: number };
};

const OFFLINE_AFTER_MIN = 75;

export function botState(last: Heartbeat | null): Ctx["state"] {
  const minutes = last ? (Date.now() - new Date(last.ts).getTime()) / 60000 : Infinity;
  const key: BotStateKey = !last ? "never" : last.status === "running" && minutes <= OFFLINE_AFTER_MIN ? "running"
    : last.status === "error" ? "error" : "idle";
  const label = { never: "jamais lancé", offline: "hors ligne", error: "erreur au dernier passage", running: "en train de clipper", idle: "en attente" }[key];
  return { key, label };
}

export const NET_LABEL: Record<string, string> = { tiktok: "TikTok", youtube: "YouTube", instagram: "Instagram" };

export function NetBadge({ net }: { net: string }) {
  return <span className={`net net-${net}`}>{NET_LABEL[net] ?? net}</span>;
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="phead">
      <div>
        <h1>{title}</h1>
        {sub && <p className="phead-sub">{sub}</p>}
      </div>
      {children && <div className="phead-actions">{children}</div>}
    </header>
  );
}

export function Kpi({ label, value, hint, tone, href }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "pink" | "violet" | "ok" | "warn" | "muted"; href?: string }) {
  const inner = (
    <>
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">{value}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </>
  );
  const cls = `kpi ${tone ? `kpi-${tone}` : ""}`;
  return href ? <a href={href} className={`${cls} kpi-link`}>{inner}</a> : <div className={cls}>{inner}</div>;
}

export function Panel({ title, sub, action, children, className = "" }: { title?: ReactNode; sub?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && <header className="panel-head">{title && <h2>{title}{sub && <small className="panel-sub">{sub}</small>}</h2>}{action}</header>}
      {children}
    </section>
  );
}

/** Message clair quand une source de données n'est pas branchée. */
export function NotConnected({ what, how }: { what: string; how: ReactNode }) {
  return (
    <div className="notconn">
      <b>{what}</b>
      <p>{how}</p>
    </div>
  );
}

export function BufferMissing() {
  return (
    <NotConnected
      what="Stats pas encore connectées"
      how={<>Les vues, likes et commentaires de TikTok et YouTube arrivent par Buffer. Il manque la clé <code>BUFFER_API_KEY</code> sur Vercel
        (à créer sur <a href="https://publish.buffer.com/settings/api" target="_blank" rel="noreferrer">publish.buffer.com/settings/api</a>). La même clé sert à publier les clips.</>}
    />
  );
}

/** Histogramme vertical en SVG : vues par post (plus récent à droite). */
export function ViewsChart({ posts, height = 180 }: { posts: PostStats[]; height?: number }) {
  const data = [...posts].sort((a, b) => a.at.localeCompare(b.at)).slice(-24);
  if (!data.length) return <p className="muted small">Aucun post publié pour l&apos;instant.</p>;
  const max = Math.max(1, ...data.map((p) => p.views));
  const slots = Math.max(data.length, 12); // peu de posts : barres fines alignées à droite
  const off = slots - data.length;
  const w = 100 / slots;
  return (
    <figure className="chart">
      <div className="chart-y" aria-hidden="true"><span>{compact(max)}</span><span>{compact(max / 2)}</span><span>0</span></div>
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" role="img" aria-label="Vues par post" style={{ height }}>
        <line x1="0" x2="100" y1={height / 2} y2={height / 2} className="chart-grid" />
        {data.map((p, i) => {
          const h = Math.max(1.5, (p.views / max) * (height - 4));
          return (
            <rect key={p.id} x={(i + off) * w + w * 0.15} width={w * 0.7} y={height - h} height={h} rx="0.6" className={`bar bar-${p.net}`}>
              <title>{`${shortDate(p.at)} · ${p.views.toLocaleString("fr-FR")} vues · ${p.text.slice(0, 60)}`}</title>
            </rect>
          );
        })}
      </svg>
      <figcaption className="chart-x">
        <span>{shortDate(data[0].at)}</span>
        <span className="legend"><i className="lg lg-tiktok" />TikTok <i className="lg lg-youtube" />YouTube</span>
        <span>{shortDate(data[data.length - 1].at)}</span>
      </figcaption>
    </figure>
  );
}

/** Barre horizontale de progression (jauges). */
export function Meter({ value, max, label, tone = "pink" }: { value: number; max: number; label: ReactNode; tone?: "pink" | "violet" | "warn" | "ko" }) {
  const p = Math.min(100, Math.round((value / Math.max(1, max)) * 100));
  return (
    <div className="meter">
      <div className="meter-top"><span>{label}</span><b>{p} %</b></div>
      <div className="meter-track"><div className={`meter-fill meter-${p >= 90 ? "ko" : p >= 70 ? "warn" : tone}`} style={{ width: `${p}%` }} /></div>
    </div>
  );
}

/** Relie chaque post Buffer au clip du bot qui l'a produit (via l'id Buffer gardé dans networks). */
export function linkPosts(stats: StatsResult, clips: Clip[]) {
  const byPost = new Map<string, Clip>();
  for (const c of clips) for (const n of Object.values(c.networks ?? {})) if (n?.id) byPost.set(n.id, c);
  const all = stats.connected && stats.ok ? stats.posts : [];
  const rows = all.map((p) => ({ ...p, clip: byPost.get(p.id) }));
  // Posts « du bot » : reliés à un clip, ou envoyés depuis la mise en route du bot
  // (les clips publiés finissent par être supprimés du stockage pour faire de la place).
  const bot = rows.filter((r) => r.clip || r.at >= BOT_START_ISO);
  return { all: rows, bot };
}
export type LinkedPost = ReturnType<typeof linkPosts>["all"][number];
