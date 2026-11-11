import AltTitles from "./AltTitles";
import CopyPost from "./CopyPost";
import { loadClips, loadHeartbeat, type Clip, type Status } from "@/lib/data";

export const dynamic = "force-dynamic";

const TABS: { key: Status; label: string }[] = [
  { key: "pending", label: "À valider" },
  { key: "approved", label: "À poster" },
  { key: "posted", label: "Publiés" },
  { key: "rejected", label: "Rejetés" },
];

const OFFLINE_AFTER_MIN = 75; // le bot tourne toutes les heures

function ago(iso?: string) {
  if (!iso) return "jamais";
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `il y a ${h} h ${String(m % 60).padStart(2, "0")}`;
  return `il y a ${Math.floor(h / 24)} j`;
}

function scoreOf(c: Clip) {
  if (c.kind === "vod_chat_spike") return { label: "Pic de chat", value: `z = ${c.chat_zscore?.toFixed(1) ?? "?"}` };
  if (c.views != null) return { label: "Clip viewer", value: `${c.views.toLocaleString("fr-FR")} vues` };
  return { label: "Manuel", value: "—" };
}

export default async function Home({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab: rawTab } = await searchParams;
  const tab = (TABS.find((t) => t.key === rawTab)?.key ?? "pending") as Status;
  const configured = !!process.env.BLOB_READ_WRITE_TOKEN;
  const [{ last, history }, clips] = await Promise.all([loadHeartbeat(), loadClips()]);

  const counts = Object.fromEntries(TABS.map((t) => [t.key, clips.filter((c) => c.status === t.key).length]));
  const shown = clips.filter((c) => c.status === tab);
  const minutes = last ? (Date.now() - new Date(last.ts).getTime()) / 60000 : Infinity;
  const state = !last ? "never" : minutes > OFFLINE_AFTER_MIN ? "offline" : last.status === "error" ? "error" : last.status === "running" ? "running" : "idle";
  const stateLabel = { never: "Jamais connecté", offline: "Hors ligne", error: "Erreur", running: "En cours", idle: "En attente du prochain passage" }[state];
  const back = `/?tab=${tab}`;

  return (
    <div className="page">
      <header className="top">
        <div className="brand">
          <span className="eyebrow">Clips GTA VI · 1 compte</span>
          <h1>GTA Clipper</h1>
        </div>
        <nav className="links">
          <a href="/frise.html">Comment ça marche</a>
          <form method="post" action="/api/logout"><button className="linkbtn">Déconnexion</button></form>
        </nav>
      </header>

      {!configured && (
        <p className="banner">Stockage non configuré : la variable BLOB_READ_WRITE_TOKEN manque sur Vercel.</p>
      )}

      <section className="status">
        <div className={`bot bot-${state}`}>
          <div className="bot-head">
            <span className="dot" aria-hidden="true" />
            <div>
              <div className="bot-state">Bot : {stateLabel}</div>
              <div className="muted">Dernier signal {ago(last?.ts)}</div>
            </div>
          </div>
          {last?.step && <div className="bot-step"><span className="muted">Étape</span> {last.step}</div>}
          {last?.message && <div className="bot-msg">{last.message}</div>}
          {last?.stats && (
            <dl className="stats">
              {Object.entries(last.stats).map(([k, v]) => (
                <div key={k}><dt>{k.replaceAll("_", " ")}</dt><dd>{v}</dd></div>
              ))}
            </dl>
          )}
          {state === "never" && (
            <p className="muted small">Lance le bot sur ton PC (<code>python -m gta_clipper run</code>) : il apparaîtra ici dès son premier passage.</p>
          )}
        </div>
        <div className="counters">
          {TABS.map((t) => (
            <a key={t.key} href={`/?tab=${t.key}`} className={`counter ${t.key === tab ? "on" : ""}`}>
              <span className="n">{counts[t.key]}</span><span>{t.label}</span>
            </a>
          ))}
        </div>
      </section>

      {history.length > 1 && (
        <details className="log">
          <summary>Activité récente du bot</summary>
          <ul>
            {history.map((h) => (
              <li key={h.ts}><span className="mono muted">{new Date(h.ts).toLocaleString("fr-FR", { timeZone: "Europe/Paris" })}</span> {h.step ?? h.status}{h.message ? ` · ${h.message}` : ""}</li>
            ))}
          </ul>
          {last?.logs?.length ? <pre>{last.logs.join("\n")}</pre> : null}
        </details>
      )}

      <section className="clips">
        {shown.length === 0 && <p className="empty">Aucun clip dans « {TABS.find((t) => t.key === tab)!.label} ».</p>}
        {shown.map((c) => {
          const s = scoreOf(c);
          const post = `${c.title}\n\n${c.description}\n\n${c.hashtags.join(" ")}`;
          return (
            <article key={c.id} className="card">
              {c.video_url
                ? <video src={c.video_url} poster={c.thumb_url} controls preload="none" playsInline />
                : <div className="novideo">Vidéo absente</div>}
              <form method="post" action="/api/decide" className="fields">
                <input type="hidden" name="id" value={c.id} />
                <input type="hidden" name="back" value={back} />
                <div className="meta">
                  <span className="streamer">{c.streamer}</span>
                  <span className="score"><span className="muted">{s.label}</span> {s.value}</span>
                  <span className="muted">{Math.round(c.duration)} s · créé {ago(c.created_at)}</span>
                  {c.source_url && <a href={c.source_url} target="_blank" rel="noreferrer">source Twitch</a>}
                </div>
                {c.confidence === "low" && <p className="warn">Titre peu sûr : vérifie qu'il colle au clip.</p>}
                <label htmlFor={`t-${c.id}`}>Titre</label>
                <input id={`t-${c.id}`} name="title" className="title" defaultValue={c.title} />
                {tab === "pending" && <AltTitles titles={c.alt_titles} inputId={`t-${c.id}`} />}
                <label htmlFor={`d-${c.id}`}>Description</label>
                <textarea id={`d-${c.id}`} name="description" rows={3} defaultValue={c.description} />
                <label htmlFor={`h-${c.id}`}>Hashtags</label>
                <input id={`h-${c.id}`} name="hashtags" defaultValue={c.hashtags.join(" ")} />
                <details className="transcript"><summary>Transcription</summary><p>{c.transcript || "(aucune parole détectée)"}</p></details>

                {tab === "pending" && (
                  <div className="actions">
                    <button className="btn ok" name="status" value="approved">Valider</button>
                    <button className="btn ko" name="status" value="rejected">Rejeter</button>
                  </div>
                )}
                {tab === "approved" && (
                  <>
                    <CopyPost text={post} />
                    {c.video_url && <a className="btn ghost" href={c.video_url} target="_blank" rel="noreferrer">Ouvrir la vidéo</a>}
                    <label htmlFor={`p-${c.id}`}>Lien du post (TikTok, Shorts…)</label>
                    <input id={`p-${c.id}`} name="post_url" placeholder="https://www.tiktok.com/@…" />
                    <div className="actions">
                      <button className="btn ok" name="status" value="posted">Marquer comme publié</button>
                      <button className="btn ghost" name="status" value="pending">Remettre à valider</button>
                    </div>
                  </>
                )}
                {tab === "posted" && (
                  <div className="actions">
                    {c.post_url ? <a className="btn ghost" href={c.post_url} target="_blank" rel="noreferrer">Voir le post</a> : <span className="muted">Pas de lien enregistré</span>}
                    <span className="muted small">Publié {ago(c.decided_at)}</span>
                  </div>
                )}
                {tab === "rejected" && (
                  <div className="actions">
                    <button className="btn ghost" name="status" value="pending">Remettre à valider</button>
                  </div>
                )}
              </form>
            </article>
          );
        })}
      </section>
    </div>
  );
}
