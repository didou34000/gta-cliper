import { BufferMissing, Kpi, NetBadge, PageHead, Panel, ViewsChart, linkPosts, type Ctx, type LinkedPost } from "../ctx";
import { NetworkLine } from "./Clips";
import { totals } from "@/lib/stats";
import { ago, compact, dayTime, pct } from "@/lib/format";

const NETS = ["tiktok", "youtube"] as const;

export default function StatsView({ ctx, scope, net }: { ctx: Ctx; scope: "bot" | "all"; net?: string }) {
  const { stats, clips } = ctx;
  const { all, bot } = linkPosts(stats, clips);
  const base = scope === "all" ? all : bot;
  const rows = net && NETS.includes(net as any) ? base.filter((p) => p.net === net) : base;
  const t = totals(rows);
  const updated = rows.map((r) => r.updatedAt).filter(Boolean).sort().pop();
  const q = (o: Record<string, string | undefined>) => {
    const p = new URLSearchParams({ v: "stats" });
    const merged = { scope: scope === "all" ? "all" : undefined, net, ...o };
    for (const [k, v] of Object.entries(merged)) if (v) p.set(k, v);
    return `/?${p}`;
  };
  // Clips marqués publiés sur le site sans passer par Buffer : pas de stats possibles.
  const linked = new Set(bot.map((p) => p.clip?.id).filter(Boolean));
  const manual = clips.filter((c) => c.status === "posted" && !linked.has(c.id));

  return (
    <>
      <PageHead
        title="Publiés & stats"
        sub={stats.connected && stats.ok
          ? <>Chiffres TikTok et YouTube lus dans Buffer. Buffer les met à jour environ une fois par jour{updated ? ` (dernière mise à jour ${ago(updated)})` : ""}.</>
          : "Vues, likes, commentaires et partages de chaque clip publié."}
      >
        {stats.connected && stats.ok && <>
        <div className="seg" role="group" aria-label="Quels posts">
          <a href={q({ scope: undefined })} className={scope === "bot" ? "on" : ""}>Clips du bot</a>
          <a href={q({ scope: "all" })} className={scope === "all" ? "on" : ""}>Tout le compte</a>
        </div>
        <div className="seg" role="group" aria-label="Réseau">
          <a href={q({ net: undefined })} className={!net ? "on" : ""}>Tous</a>
          {NETS.map((n) => <a key={n} href={q({ net: n })} className={net === n ? "on" : ""}>{n === "tiktok" ? "TikTok" : "YouTube"}</a>)}
        </div>
        </>}
      </PageHead>

      {!stats.connected ? <Panel><BufferMissing /></Panel>
        : !stats.ok ? <p className="banner">Buffer a répondu une erreur : {stats.error}. Les stats reviendront au prochain chargement.</p>
        : <>
            <div className="kpis kpis-6">
              <Kpi label="Posts" value={t.posts} />
              <Kpi label="Vues" tone="pink" value={compact(t.views)} hint={t.posts ? `${compact(t.views / t.posts)} par post` : undefined} />
              <Kpi label="Likes" value={compact(t.likes)} />
              <Kpi label="Commentaires" value={compact(t.comments)} />
              <Kpi label="Partages" value={compact(t.shares)} />
              <Kpi label="Engagement moyen" tone="violet" value={pct(t.eng)} hint="interactions ÷ vues" />
            </div>

            {!net && (
              <div className="grid-2">
                {NETS.map((n) => {
                  const nt = totals(base.filter((p) => p.net === n));
                  return (
                    <Panel key={n} title={<><NetBadge net={n} /> {n === "tiktok" ? "@gta6francenews" : "GTA 6 FRANCE"}</>}>
                      {nt.posts ? (
                        <ul className="facts facts-cols">
                          <li><span>Posts</span><b>{nt.posts}</b></li>
                          <li><span>Vues</span><b>{compact(nt.views)}</b></li>
                          <li><span>Vues / post</span><b>{compact(nt.views / nt.posts)}</b></li>
                          <li><span>Likes</span><b>{compact(nt.likes)}</b></li>
                          <li><span>Commentaires</span><b>{compact(nt.comments)}</b></li>
                          <li><span>Engagement</span><b>{pct(nt.eng)}</b></li>
                        </ul>
                      ) : <p className="muted small">Aucun post {scope === "bot" ? "du bot " : ""}sur ce réseau pour l&apos;instant.</p>}
                    </Panel>
                  );
                })}
              </div>
            )}

            <Panel title="Vues par post (24 derniers)">
              <ViewsChart posts={rows} />
            </Panel>

            <Panel title={`Détail des posts (${rows.length})`}>
              {!rows.length
                ? <p className="muted small">{scope === "bot" ? "Aucun clip du bot publié pour l'instant. Passe sur « Tout le compte » pour voir les anciens posts." : "Aucun post envoyé trouvé dans Buffer."}</p>
                : <PostTable rows={rows} />}
            </Panel>
          </>}

      {manual.length > 0 && (
        <Panel title={stats.connected && stats.ok ? `Publiés à la main (${manual.length})` : `Clips publiés (${manual.length})`}>
          <p className="muted small">{stats.connected && stats.ok
            ? "Ces clips ont été marqués publiés sur le site sans passer par Buffer : pas de stats automatiques pour eux."
            : "Leurs vues et likes s'afficheront ici dès que Buffer sera connecté."}</p>
          <ul className="plain">
            {manual.map((c) => (
              <li key={c.id}>
                <b>{c.title}</b> <span className="muted small">· {c.streamer} · {ago(c.decided_at)}</span>
                {c.post_url && <> · <a href={c.post_url} target="_blank" rel="noreferrer">voir le post</a></>}
                <NetworkLine c={c} />
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}

function PostTable({ rows }: { rows: LinkedPost[] }) {
  const best = Math.max(...rows.map((r) => r.views));
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Post</th><th>Réseau</th><th className="num">Vues</th><th className="num">Likes</th>
            <th className="num">Comm.</th><th className="num">Partages</th><th className="num">Eng.</th><th className="num">Visionnage moy.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td className="t-post">
                {r.thumb ? <img src={r.thumb} alt="" loading="lazy" /> : <span className="t-noimg" />}
                <span>
                  <b>{r.clip?.title || r.text.split("\n")[0].slice(0, 90) || "(sans texte)"}</b>
                  <small className="muted">{dayTime(r.at)}{r.clip ? ` · ${r.clip.streamer}` : ""}
                    {r.url && <> · <a href={r.url} target="_blank" rel="noreferrer">ouvrir</a></>}</small>
                </span>
              </td>
              <td data-l="Réseau"><NetBadge net={r.net} /></td>
              <td className="num" data-l="Vues"><b className={r.views === best && best > 0 ? "tx-pink" : ""}>{compact(r.views)}</b></td>
              <td className="num" data-l="Likes">{compact(r.likes)}</td>
              <td className="num" data-l="Comm.">{compact(r.comments)}</td>
              <td className="num" data-l="Partages">{compact(r.shares)}</td>
              <td className="num" data-l="Eng.">{pct(r.engagement)}</td>
              <td className="num" data-l="Visionnage">{r.avgWatch ? `${r.avgWatch.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} s` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
