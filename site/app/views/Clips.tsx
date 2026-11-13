import AltTitles from "../AltTitles";
import CopyPost from "../CopyPost";
import { NET_LABEL, PageHead, type Ctx } from "../ctx";
import type { Clip, RunInfo } from "@/lib/data";
import { bufferReady, publishEnabled } from "@/lib/buffer";
import { ago, dayTime, fmtHoursShort, fmtMin } from "@/lib/format";

function runParams(r: RunInfo) {
  return [
    r.game,
    r.source ? "vidéo YouTube" : r.top ? `top ${r.top} streamers` : "streamers choisis",
    r.max_clips ? `${r.max_clips} clips max` : "",
    r.min_views != null ? `≥ ${r.min_views.toLocaleString("fr-FR")} vues` : "",
    r.hours ? `clips des ${fmtHoursShort(r.hours)}` : "",
  ].filter(Boolean).join(" · ");
}

// Clips rangés par passage (le plus récent d'abord), puis par potentiel dans le passage.
function groupByRun(clips: Clip[]) {
  const groups = new Map<string, { run?: RunInfo; clips: Clip[] }>();
  for (const c of clips) {
    const key = c.run?.id ?? "avant";
    const g = groups.get(key) ?? { run: c.run, clips: [] };
    g.clips.push(c);
    groups.set(key, g);
  }
  const rankKey = (c: Clip) => [-(c.potential ?? 0), c.rank ?? 99, -(c.views ?? 0)];
  for (const g of groups.values()) {
    g.clips.sort((a, b) => {
      const ka = rankKey(a), kb = rankKey(b);
      for (let i = 0; i < ka.length; i++) if (ka[i] !== kb[i]) return ka[i] - kb[i];
      return 0;
    });
  }
  return [...groups.values()].sort((a, b) => (b.run ? +new Date(b.run.at) : 0) - (a.run ? +new Date(a.run.at) : 0));
}

function scoreOf(c: Clip) {
  if (c.kind === "vod_chat_spike") return `pic de chat z = ${c.chat_zscore?.toFixed(1) ?? "?"}`;
  if (c.kind === "youtube") return "vidéo YouTube";
  if (c.views != null) return `${c.views.toLocaleString("fr-FR")} vues Twitch`;
  return "manuel";
}

export function NetworkLine({ c }: { c: Clip }) {
  const nets = Object.entries(c.networks ?? {});
  if (!nets.length) return null;
  const hm = (iso?: string) => iso ? dayTime(iso) : "";
  return (
    <div className="netline">
      {nets.map(([k, n]) => {
        if (!n) return null;
        const label = NET_LABEL[k] ?? k;
        const cls = n.state === "error" ? "ko" : n.state === "scheduled" ? "wait" : "ok";
        const txt = n.state === "error" ? `${label} : ${n.error}`
          : n.state === "scheduled" ? (n.due && +new Date(n.due) <= Date.now() ? `${label} : envoyé à Buffer (${hm(n.due)})` : `${label} : programmé ${hm(n.due)}`)
          : `${label} : publié`;
        return <span key={k} className={`chip chip-${cls}`}>{txt}</span>;
      })}
    </div>
  );
}

export default async function ClipsView({ ctx, status }: { ctx: Ctx; status: "pending" | "approved" }) {
  const shown = ctx.clips.filter((c) => c.status === status);
  const back = `/?v=${status === "pending" ? "valider" : "poster"}`;
  const pending = status === "pending";
  const pubOn = bufferReady() && (await publishEnabled());

  return (
    <>
      <PageHead
        title={pending ? "À valider" : "À poster"}
        sub={pending
          ? <>Vérifie le titre, corrige si besoin, puis <b>Valider</b>. <b>Rejeter</b> supprime le clip pour de bon.
              {ctx.schedule.auto_min ? <> Les clips notés ≥ {ctx.schedule.auto_min}/10 sont validés tout seuls.</> : null}</>
          : pubOn
            ? <>Les clips validés partent tout seuls sur TikTok et YouTube via Buffer, un toutes les {fmtMin(ctx.schedule.publish_every_min)} (10 programmés max).</>
            : <>Publication auto {bufferReady() ? <>coupée (<a href="/?v=programmation">l'allumer</a>)</> : "pas encore branchée (clé Buffer manquante)"} : rien ne part tout seul. Copie le texte, poste à la main, puis colle le lien.</>}
      />

      {shown.length === 0 && (
        <div className="empty">
          <b>{pending ? "Rien à valider" : "File vide"}</b>
          <p>{pending ? "Le prochain passage du bot ramènera des clips ici." : "Les clips que tu valides arrivent ici avant de partir sur les réseaux."}</p>
        </div>
      )}

      {groupByRun(shown).map((g) => (
        <section key={g.run?.id ?? "avant"} className="run-group">
          <header className="run-head">
            {g.run
              ? <><b>Passage du {dayTime(g.run.at)}</b>
                  <span className={`tag ${g.run.trigger === "programmé" ? "tag-auto" : "tag-manual"}`}>{g.run.trigger}</span>
                  <span className="muted small">{runParams(g.run)}</span></>
              : <b>Passages plus anciens</b>}
            <span className="run-count">{g.clips.length} clip{g.clips.length > 1 ? "s" : ""}</span>
          </header>
          <div className="clips">
            {g.clips.map((c, i) => {
              const post = `${c.title}\n\n${c.description}\n\n${c.hashtags.join(" ")}`;
              return (
                <article key={c.id} className="card">
                  <div className="card-media">
                    {c.video_url
                      ? <video src={c.video_url} poster={c.thumb_url} controls preload="none" playsInline />
                      : <div className="novideo">Vidéo absente</div>}
                  </div>
                  <form method="post" action="/api/decide" className="fields">
                    <input type="hidden" name="id" value={c.id} />
                    <input type="hidden" name="back" value={back} />
                    <div className="meta">
                      <span className="rankpos">#{i + 1}</span>
                      <span className="streamer">{c.streamer}</span>
                      {c.potential ? <span className={`pot pot-${c.potential >= 8 ? "hi" : c.potential >= 5 ? "mid" : "lo"}`} title={c.potential_reason || ""}>{c.potential}/10</span> : null}
                    </div>
                    <div className="meta muted small">
                      <span>{scoreOf(c)}</span>
                      <span>{Math.round(c.duration)} s</span>
                      <span>créé {ago(c.created_at)}</span>
                      {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer">source Twitch</a>}
                    </div>
                    {c.potential_reason && <p className="why">{c.potential_reason}</p>}
                    {c.confidence === "low" && <p className="warn">Titre peu sûr : vérifie qu&apos;il colle au clip.</p>}
                    <label htmlFor={`t-${c.id}`}>Titre</label>
                    <input id={`t-${c.id}`} name="title" className="title" defaultValue={c.title} />
                    {pending && <AltTitles titles={c.alt_titles} inputId={`t-${c.id}`} />}
                    <label htmlFor={`d-${c.id}`}>Description</label>
                    <textarea id={`d-${c.id}`} name="description" rows={3} defaultValue={c.description} />
                    <label htmlFor={`h-${c.id}`}>Hashtags</label>
                    <input id={`h-${c.id}`} name="hashtags" defaultValue={c.hashtags.join(" ")} />
                    <details className="transcript"><summary>Transcription</summary><p>{c.transcript || "(aucune parole détectée)"}</p></details>

                    {pending ? (
                      <div className="actions">
                        <button className="btn ok" name="status" value="approved">Valider</button>
                        <button className="btn ko" name="status" value="rejected" title="Supprime définitivement le clip">Rejeter (supprime)</button>
                      </div>
                    ) : (
                      <>
                        <NetworkLine c={c} />
                        <div className="actions">
                          <CopyPost text={post} />
                          {c.video_url && <a className="btn ghost" href={c.video_url} target="_blank" rel="noreferrer">Ouvrir la vidéo</a>}
                        </div>
                        <label htmlFor={`p-${c.id}`}>Lien du post (si publié à la main)</label>
                        <input id={`p-${c.id}`} name="post_url" placeholder="https://www.tiktok.com/@…" />
                        <div className="actions">
                          <button className="btn ok" name="status" value="posted">Marquer comme publié</button>
                          <button className="btn ghost" name="status" value="pending">Remettre à valider</button>
                        </div>
                      </>
                    )}
                  </form>
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </>
  );
}
