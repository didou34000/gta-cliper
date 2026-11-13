import LiveBar from "./LiveBar";
import { latestRun } from "@/lib/github";
import { loadClipsAndSize, loadHeartbeat } from "@/lib/data";
import { loadSchedule } from "@/lib/schedule";
import { countPage, flushSiteOps, r2Configured } from "@/lib/r2";
import { loadUsage } from "@/lib/usage";
import { loadStats } from "@/lib/stats";
import { botState, type Ctx } from "./ctx";
import Overview from "./views/Overview";
import ClipsView from "./views/Clips";
import StatsView from "./views/Stats";
import BotView from "./views/Bot";
import ProgView from "./views/Programmation";
import SettingsView from "./views/Settings";

export const dynamic = "force-dynamic";

type View = "accueil" | "valider" | "poster" | "stats" | "bot" | "programmation" | "reglages";

const NAV: { key: View; label: string; icon: string; group: string }[] = [
  { key: "accueil", label: "Vue d'ensemble", icon: "◎", group: "Pilotage" },
  { key: "valider", label: "À valider", icon: "✓", group: "Clips" },
  { key: "poster", label: "À poster", icon: "↗", group: "Clips" },
  { key: "stats", label: "Publiés & stats", icon: "▮", group: "Clips" },
  { key: "bot", label: "Suivi du bot", icon: "●", group: "Bot" },
  { key: "programmation", label: "Lancer le bot", icon: "◷", group: "Bot" },
  { key: "reglages", label: "Consommation & quotas", icon: "⚙", group: "Bot" },
];

// Anciens liens (?tab=pending…) toujours valables.
const LEGACY: Record<string, View> = { pending: "valider", approved: "poster", posted: "stats" };

type Search = { sent?: string; v?: string; tab?: string; launch?: string; prog?: string; yt?: string; scope?: string; net?: string };

export default async function Home({ searchParams }: { searchParams: Promise<Search> }) {
  const sp = await searchParams;
  const want = sp.v ?? (sp.tab ? LEGACY[sp.tab] : undefined) ?? (sp.launch || sp.prog ? "programmation" : "accueil");
  const view = (NAV.find((n) => n.key === want)?.key ?? "accueil") as View;

  countPage();
  const [{ last }, { clips, bytes }, { schedule, lastRun }, stats, run, usage] = await Promise.all([
    loadHeartbeat(), loadClipsAndSize(), loadSchedule(), loadStats(), latestRun(),
    view === "reglages" ? loadUsage() : Promise.resolve(null),
  ]);
  await flushSiteOps().catch(() => {});
  const sent = /^\d{13}$/.test(sp.sent ?? "") ? Number(sp.sent) : undefined;
  const state = botState(last);
  const ctx: Ctx = {
    clips, bytes, last, state, schedule, lastRun, stats,
    configured: r2Configured(),
    counts: {
      pending: clips.filter((c) => c.status === "pending").length,
      approved: clips.filter((c) => c.status === "approved").length,
      posted: clips.filter((c) => c.status === "posted").length,
    },
    nextRun: schedule.enabled
      ? (lastRun ? new Date(Math.max(Date.now(), +new Date(lastRun) + schedule.every_min * 60000)) : new Date())
      : null,
  };
  const badge: Partial<Record<View, number>> = { valider: ctx.counts.pending, poster: ctx.counts.approved };
  const groups = [...new Set(NAV.map((n) => n.group))];

  return (
    <div className="shell">
      <aside className="side">
        <a href="/" className="logo">
          <span className="logo-mark">VI</span>
          <span className="logo-txt"><b>GTA Clipper</b><small>@gta6francenews</small></span>
        </a>
        <p className={`side-bot bot-${state.key}`}>
          <span className="dot" aria-hidden="true" />
          <span>Bot : <b>{state.label}</b></span>
        </p>
        <nav className="nav" aria-label="Sections">
          {groups.map((g) => (
            <div key={g} className="nav-group">
              <span className="nav-title">{g}</span>
              {NAV.filter((n) => n.group === g).map((n) => (
                <a key={n.key} href={`/?v=${n.key}`} className={n.key === view ? "on" : ""} aria-current={n.key === view ? "page" : undefined}>
                  <span className="nav-ico" aria-hidden="true">{n.icon}</span>
                  <span>{n.label}</span>
                  {badge[n.key] ? <span className="nav-badge">{badge[n.key]}</span> : null}
                </a>
              ))}
            </div>
          ))}
        </nav>
        <a href="/frise.html" className="side-help">Comment ça marche</a>
        <form method="post" action="/api/logout" className="side-logout"><button type="submit">Déconnexion</button></form>
      </aside>

      <main className="main">
        <LiveBar key={sent ?? 0} initial={{ run, beat: last, now: new Date().toISOString() }} sent={sent} full={view === "bot"} />
        {!ctx.configured && <p className="banner">Stockage non configuré : les clés R2 (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_PUBLIC_URL) manquent sur Vercel.</p>}
        {view === "accueil" && <Overview ctx={ctx} />}
        {view === "valider" && <ClipsView ctx={ctx} status="pending" />}
        {view === "poster" && <ClipsView ctx={ctx} status="approved" />}
        {view === "stats" && <StatsView ctx={ctx} scope={sp.scope === "all" ? "all" : "bot"} net={sp.net} />}
        {view === "bot" && <BotView ctx={ctx} />}
        {view === "programmation" && <ProgView ctx={ctx} launch={sp.launch} prog={sp.prog} yt={sp.yt} />}
        {view === "reglages" && usage && <SettingsView ctx={ctx} usage={usage} />}
      </main>
    </div>
  );
}
