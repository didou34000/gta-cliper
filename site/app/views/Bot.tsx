import { PageHead, Panel, type Ctx } from "../ctx";
import { ago, hhmmss } from "@/lib/format";

const NODES: { key: string; label: string; sub: string; stat?: string; view?: string; count?: "pending" | "approved" | "posted" }[] = [
  { key: "twitch", label: "Twitch", sub: "clips des plus gros streamers FR", stat: "clips_trouves" },
  { key: "scoring", label: "Tri", sub: "vues, durée, note de potentiel /10" },
  { key: "transcription", label: "Transcription", sub: "Whisper, mot à mot" },
  { key: "titre", label: "Titre IA", sub: "titre, accroche, hashtags" },
  { key: "render", label: "Montage 9:16", sub: "accroche + sous-titres roses", stat: "clips_produits" },
  { key: "site", label: "À valider", sub: "ton OK (ou auto)", view: "valider", count: "pending" },
  { key: "approved", label: "À poster", sub: "file Buffer", view: "poster", count: "approved" },
  { key: "posted", label: "Publié", sub: "TikTok + YouTube", view: "stats", count: "posted" },
];
const NODE_LABEL: Record<string, string> = Object.fromEntries(NODES.map((n) => [n.key, n.label]));

export default function BotView({ ctx }: { ctx: Ctx }) {
  const { last, state, counts } = ctx;
  const running = state.key === "running";

  return (
    <>
      <PageHead
        title="Bot en direct"
        sub={<>Dernier signal {ago(last?.ts)}{last?.step ? ` · ${last.step}` : ""}{last?.message ? ` · ${last.message}` : ""}{running ? " · la page se rafraîchit toute seule" : ""}</>}
      />

      <section className="flow" aria-label="Chaîne de fabrication">
        {NODES.map((n, i) => {
          const active = running && last?.node === n.key;
          const count = n.count ? counts[n.count] : n.stat ? last?.stats?.[n.stat] : undefined;
          const inner = (
            <>
              <span className="node-step">{String(i + 1).padStart(2, "0")}</span>
              <span className="node-title">{n.label}</span>
              <span className="node-sub">{n.sub}</span>
              {active && last?.streamer && <span className="node-now">{last.streamer}</span>}
              {count !== undefined && <span className="node-count">{count}</span>}
            </>
          );
          return (
            <div key={n.key} className="flow-item">
              {n.view
                ? <a href={`/?v=${n.view}`} className={`node node-link ${active ? "active" : ""}`}>{inner}</a>
                : <div className={`node ${active ? "active" : ""}`}>{inner}</div>}
              {i < NODES.length - 1 && <span className="arrow" aria-hidden="true" />}
            </div>
          );
        })}
      </section>

      {last?.streamers && Object.keys(last.streamers).length > 0 ? (
        <Panel title="Streamers du dernier passage">
          <div className="streamers">
            {Object.entries(last.streamers).map(([name, s0]) => {
              // Passage fini : une carte restée « en attente » / « en cours » est en réalité terminée.
              const s = !running && ["en attente", "en cours", "arrêté"].includes(s0.etat)
                ? { ...s0, etat: s0.produits ? "fini" : s0.erreurs ? "erreur" : "non retenu" } : s0;
              return (
                <div key={name} className={`st st-${s.etat.replace(/\s/g, "-")} ${last.streamer === name && running ? "st-now" : ""}`}>
                  <div className="st-head"><b>{name}</b><span className="st-state">{s.etat}</span></div>
                  <div className="st-nums">
                    <span><b>{s.clips_vus}</b> vus</span>
                    <span><b>{s.retenus}</b> retenus</span>
                    {s.pics_chat > 0 && <span><b>{s.pics_chat}</b> pics de chat</span>}
                    <span><b>{s.produits}</b> produits</span>
                    {s.deja_faits > 0 && <span><b>{s.deja_faits}</b> déjà faits</span>}
                    {s.erreurs > 0 && <span className="st-err"><b>{s.erreurs}</b> erreur{s.erreurs > 1 ? "s" : ""}</span>}
                  </div>
                  {s.action && <div className="st-action">{s.action}{s.ts ? <span className="muted"> · {ago(s.ts)}</span> : null}</div>}
                </div>
              );
            })}
          </div>
        </Panel>
      ) : (
        <Panel><p className="muted small">Pas encore de passage enregistré. Lance-en un depuis <a href="/?v=programmation">Programmation</a>.</p></Panel>
      )}

      {last?.events?.length ? (
        <Panel title={`Journal (${last.events.length} dernières actions)`}>
          <ol className="journal">
            {last.events.map((e, i) => (
              <li key={i} className={`ev ev-${e.level}`}>
                <time className="mono">{hhmmss(e.ts)}</time>
                {e.streamer ? <span className="ev-who">{e.streamer}</span> : <span className="ev-who muted">bot</span>}
                {e.node && <span className="ev-node">{NODE_LABEL[e.node] ?? e.node}</span>}
                <span className="ev-text">{e.text}</span>
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}

      {last?.logs?.length ? (
        <details className="panel logs"><summary>Logs techniques du bot</summary><pre>{last.logs.join("\n")}</pre></details>
      ) : null}
    </>
  );
}
