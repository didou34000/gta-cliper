import { PageHead, Panel, type Ctx } from "../ctx";
import { ago } from "@/lib/format";

// Le suivi pas à pas (étapes + journal) est dans la barre en direct, en haut de la page.
export default function BotView({ ctx }: { ctx: Ctx }) {
  const { last, state, counts } = ctx;
  const running = state.key === "running";

  return (
    <>
      <PageHead
        title="Suivi du bot"
        sub={<>Ce que fait le bot en ce moment, étape par étape. Dernier signal {ago(last?.ts)}. La page se met à jour toute seule.</>}
      >
        <a href="/?v=programmation" className="btn-primary">Lancer quelque chose</a>
      </PageHead>

      <div className="kpis kpis-3">
        <a href="/?v=valider" className="kpi kpi-link kpi-violet"><span className="kpi-label">À valider</span><span className="kpi-value">{counts.pending}</span><span className="kpi-hint">clips qui attendent ton OK</span></a>
        <a href="/?v=poster" className="kpi kpi-link"><span className="kpi-label">À poster</span><span className="kpi-value">{counts.approved}</span><span className="kpi-hint">validés, en file Buffer</span></a>
        <a href="/?v=stats" className="kpi kpi-link"><span className="kpi-label">Publiés</span><span className="kpi-value">{counts.posted}</span><span className="kpi-hint">sur TikTok et YouTube</span></a>
      </div>

      {last?.streamers && Object.keys(last.streamers).length > 0 && (
        <Panel title={running ? "Streamers de ce passage" : "Streamers du dernier passage"}>
          <div className="streamers">
            {Object.entries(last.streamers).map(([name, s0]) => {
              const s = !running && ["en attente", "en cours", "arrêté"].includes(s0.etat)
                ? { ...s0, etat: s0.produits ? "fini" : s0.erreurs ? "erreur" : "non retenu" } : s0;
              return (
                <div key={name} className={`st st-${s.etat.replace(/\s/g, "-")} ${last.streamer === name && running ? "st-now" : ""}`}>
                  <div className="st-head"><b>{name}</b><span className="st-state">{s.etat}</span></div>
                  <div className="st-nums">
                    <span><b>{s.clips_vus}</b> clips vus</span>
                    <span><b>{s.retenus}</b> gardés</span>
                    <span><b>{s.produits}</b> montés</span>
                    {s.deja_faits > 0 && <span><b>{s.deja_faits}</b> déjà faits</span>}
                    {s.erreurs > 0 && <span className="st-err"><b>{s.erreurs}</b> erreur{s.erreurs > 1 ? "s" : ""}</span>}
                  </div>
                  {s.action && <div className="st-action">{s.action}{s.ts ? <span className="muted"> · {ago(s.ts)}</span> : null}</div>}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {last?.logs?.length ? (
        <details className="panel logs"><summary>Logs techniques du dernier passage</summary><pre>{last.logs.join("\n")}</pre></details>
      ) : null}
    </>
  );
}
