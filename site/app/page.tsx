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

const NODES: { key: string; label: string; sub: string; stat?: string; tab?: Status }[] = [
  { key: "twitch", label: "Twitch", sub: "clips + VODs des streamers", stat: "clips_trouves" },
  { key: "scoring", label: "Scoring", sub: "vues ≥ 200 · pic de chat z ≥ 3" },
  { key: "transcription", label: "Transcription", sub: "Whisper, mot à mot" },
  { key: "render", label: "Vertical + sous-titres", sub: "9:16, mot actif en jaune" },
  { key: "titre", label: "Titre IA", sub: "titre, description, hashtags", stat: "clips_produits" },
  { key: "site", label: "À valider", sub: "ton OK", tab: "pending" },
  { key: "approved", label: "À poster", sub: "copier, publier", tab: "approved" },
  { key: "posted", label: "Publié", sub: "lien du post", tab: "posted" },
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
  const [{ last }, clips] = await Promise.all([loadHeartbeat(), loadClips()]);

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
        </nav>
      </header>

      {!configured && (
        <p className="banner">Stockage non configuré : la variable BLOB_READ_WRITE_TOKEN manque sur Vercel.</p>
      )}

      <p className={`botline bot-${state}`}>
        <span className="dot" aria-hidden="true" />
        <b>Bot : {stateLabel}</b>
        <span className="muted">· dernier signal {ago(last?.ts)}{last?.step ? ` · ${last.step}` : ""}{last?.message ? ` · ${last.message}` : ""}</span>
      </p>

      <section className="flow" aria-label="Pipeline">
        {NODES.map((n, i) => {
          const active = state === "running" && last?.node === n.key;
          const count = n.tab ? counts[n.tab] : n.stat ? last?.stats?.[n.stat] : undefined;
          const inner = (
            <>
              <span className="node-title">{n.label}</span>
              <span className="node-sub">{n.sub}</span>
              {count !== undefined && <span className="node-count">{count}</span>}
            </>
          );
          return (
            <div key={n.key} className="flow-item">
              {n.tab
                ? <a href={`/?tab=${n.tab}`} className={`node node-tab ${active ? "active" : ""} ${tab === n.tab ? "on" : ""}`}>{inner}</a>
                : <div className={`node ${active ? "active" : ""}`}>{inner}</div>}
              {i < NODES.length - 1 && <span className="arrow" aria-hidden="true" />}
            </div>
          );
        })}
      </section>

      <div className="tabs">
        {TABS.map((t) => (
          <a key={t.key} href={`/?tab=${t.key}`} className={t.key === tab ? "on" : ""}>{t.label} ({counts[t.key]})</a>
        ))}
        {last?.logs?.length ? (
          <details className="log"><summary>Logs du bot</summary><pre>{last.logs.join("\n")}</pre></details>
        ) : null}
      </div>

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
