import { BufferMissing, Kpi, NetBadge, PageHead, Panel, ViewsChart, linkPosts, type Ctx } from "../ctx";
import { totals } from "@/lib/stats";
import { ago, compact, dayTime, fmtMin, hhmm, inFuture, pct } from "@/lib/format";

export default function Overview({ ctx }: { ctx: Ctx }) {
  const { clips, stats, last, state, schedule, counts } = ctx;
  const { all, bot } = linkPosts(stats, clips);
  const t = totals(bot);
  const since7 = Date.now() - 7 * 86400_000;
  const t7 = totals(bot.filter((p) => +new Date(p.at) >= since7));
  const connected = stats.connected && stats.ok;

  const nextPost = clips.flatMap((c) => Object.values(c.networks ?? {}))
    .filter((n) => n?.state === "scheduled" && n.due && +new Date(n.due) > Date.now())
    .map((n) => n!.due!).sort()[0];
  const top = [...bot].sort((a, b) => b.views - a.views).slice(0, 5);
  const pending = clips.filter((c) => c.status === "pending")
    .sort((a, b) => (b.potential ?? 0) - (a.potential ?? 0)).slice(0, 4);
  const chartPosts = bot.length ? bot : all;

  return (
    <>
      <PageHead
        title="Vue d'ensemble"
        sub={<>Dernier signal du bot {ago(last?.ts)}{last?.message ? ` · ${last.message}` : ""}</>}
      >
        <a href="/?v=programmation" className="btn-primary">Lancer un passage</a>
      </PageHead>

      <div className="kpis">
        <Kpi label="Vues (clips du bot)" tone="pink" value={connected ? compact(t.views) : "—"}
          hint={connected ? `${compact(t7.views)} ces 7 derniers jours` : "Buffer pas connecté"} href="/?v=stats" />
        <Kpi label="Likes" value={connected ? compact(t.likes) : "—"}
          hint={connected ? `engagement moyen ${pct(t.eng)}` : "Buffer pas connecté"} href="/?v=stats" />
        <Kpi label="Publiés" value={connected ? t.posts : counts.posted}
          hint={connected ? `${t7.posts} cette semaine` : "marqués publiés sur le site"} href="/?v=stats" />
        <Kpi label="À valider" tone={counts.pending ? "violet" : "muted"} value={counts.pending} hint="clips qui attendent ton OK" href="/?v=valider" />
        <Kpi label="À poster" value={counts.approved}
          hint={nextPost ? `prochain post ${inFuture(nextPost)} (${hhmm(nextPost)})` : "rien de programmé"} href="/?v=poster" />
      </div>

      <div className="grid-2">
        <Panel title="Vues par post" action={<a href="/?v=stats" className="link">Tout voir</a>}>
          {!stats.connected ? <BufferMissing />
            : !stats.ok ? <p className="warn">Buffer a répondu une erreur : {stats.error}</p>
            : <>
                {!bot.length && all.length > 0 && <p className="muted small">Pas encore de clip du bot publié : voici les anciens posts du compte.</p>}
                <ViewsChart posts={chartPosts} />
              </>}
        </Panel>

        <Panel title="Le bot">
          <ul className="facts">
            <li><span>État</span><b className={`tx-${state.key}`}>{state.label}</b></li>
            <li><span>Étape</span><b>{last?.step ?? "—"}</b></li>
            <li><span>Programmation</span>
              <b>{schedule.enabled ? `toutes les ${fmtMin(schedule.every_min)}` : "arrêtée"}</b></li>
            <li><span>Prochain passage</span><b>{ctx.nextRun ? hhmm(ctx.nextRun.toISOString()) : "—"}</b></li>
            <li><span>Dernier passage programmé</span><b>{ctx.lastRun ? ago(ctx.lastRun) : "jamais"}</b></li>
            <li><span>Validation auto</span><b>{schedule.auto_min ? `potentiel ≥ ${schedule.auto_min}/10` : "non"}</b></li>
            <li><span>Rythme de publication</span><b>1 clip / {fmtMin(schedule.publish_every_min)}</b></li>
          </ul>
          <div className="row-links">
            <a href="/?v=bot" className="link">Suivre en direct</a>
            <a href="/?v=programmation" className="link">Régler</a>
          </div>
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="Meilleurs clips publiés">
          {!connected ? <p className="muted small">Le classement apparaîtra quand Buffer sera connecté.</p>
            : !top.length ? <p className="muted small">Aucun clip du bot publié pour l&apos;instant.</p>
            : <ol className="toplist">
                {top.map((p, i) => (
                  <li key={p.id}>
                    <span className="toplist-n">{i + 1}</span>
                    <span className="toplist-t">
                      <b>{p.clip?.title || p.text.split("\n")[0].slice(0, 90)}</b>
                      <small><NetBadge net={p.net} /> {dayTime(p.at)}</small>
                    </span>
                    <span className="toplist-v">{compact(p.views)}<small>vues</small></span>
                  </li>
                ))}
              </ol>}
        </Panel>

        <Panel title="À valider en priorité" action={counts.pending ? <a href="/?v=valider" className="link">Tout valider</a> : null}>
          {!pending.length ? <p className="muted small">Rien à valider. Le prochain passage en ramènera.</p>
            : <div className="mini-clips">
                {pending.map((c) => (
                  <a key={c.id} href="/?v=valider" className="mini">
                    {c.thumb_url ? <img src={c.thumb_url} alt="" loading="lazy" /> : <span className="mini-noimg" />}
                    <span className="mini-t">{c.title}</span>
                    <span className="mini-m">{c.streamer}{c.potential ? ` · ${c.potential}/10` : ""}</span>
                  </a>
                ))}
              </div>}
        </Panel>
      </div>
    </>
  );
}
