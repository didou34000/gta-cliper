// Données factices pour voir le site en local sans stockage : DEMO_DATA=1 npm run dev
// Jamais utilisé en production.
import type { Clip, Heartbeat } from "./data";
import type { LiveRun } from "./github";

export const demoOn = () => process.env.DEMO_DATA === "1" && process.env.NODE_ENV !== "production";

const now = Date.now();
const iso = (minAgo: number) => new Date(now - minAgo * 60000).toISOString();
const run = { id: "123", at: iso(30), trigger: "manuel", game: "Grand Theft Auto VI", top: 8, max_clips: 3, min_views: 200, hours: 48 };

export const DEMO_CLIPS: Clip[] = [
  { id: "a", streamer: "Squeezie", title: "Squeezie découvre les stations essence sur GTA 6", alt_titles: ["Squeezie paie son essence sur GTA 6"], description: "Squeezie tombe sur une station essence.", hashtags: ["#GTA6", "#Squeezie"], confidence: "high", kind: "twitch_clip", views: 4210, duration: 38, transcript: "", created_at: iso(20), status: "pending", run, rank: 1, potential: 8, potential_reason: "réaction forte, découverte claire" },
  { id: "b", streamer: "Gotaga", title: "Gotaga se fait braquer en 10 secondes sur GTA 6", alt_titles: [], description: "", hashtags: ["#GTA6"], confidence: "medium", kind: "twitch_clip", views: 1800, duration: 44, transcript: "", created_at: iso(22), status: "pending", run, rank: 2, potential: 6, potential_reason: "action rapide" },
  { id: "c", streamer: "ZeratoR", title: "ZeratoR teste la police de GTA 6", alt_titles: [], description: "", hashtags: ["#GTA6"], confidence: "medium", kind: "youtube", duration: 52, transcript: "", created_at: iso(200), status: "approved", run: { ...run, id: "122", trigger: "lien YouTube", source: "https://youtu.be/x" }, potential: 7 },
];

export const DEMO_BEAT: Heartbeat = {
  ts: iso(0.2), status: "running", step: "Transcription", node: "transcription", streamer: "Squeezie",
  message: "Transcription Whisper de 38 s de vidéo",
  stats: { clips_trouves: 14, clips_produits: 1, erreurs: 0 },
  streamers: { Squeezie: { etat: "en cours", clips_vus: 9, retenus: 4, deja_faits: 1, produits: 1, erreurs: 0, pics_chat: 0, action: "Transcription", ts: iso(0.2) },
               Gotaga: { etat: "en attente", clips_vus: 6, retenus: 2, deja_faits: 0, produits: 0, erreurs: 0, pics_chat: 0, action: "", ts: iso(2) } },
  events: [
    { ts: iso(3), streamer: "", node: "twitch", text: "Recherche des 8 plus gros streamers FR sur Grand Theft Auto VI", level: "info" },
    { ts: iso(2), streamer: "", node: "scoring", text: "Classement : Squeezie 8/10 · Gotaga 6/10", level: "info" },
    { ts: iso(1), streamer: "Squeezie", node: "twitch", text: "Téléchargé (12.1 Mo)", level: "info" },
    { ts: iso(0.2), streamer: "Squeezie", node: "transcription", text: "Transcription Whisper de 38 s de vidéo (modèle large-v3-turbo, sur cpu)", level: "info" },
  ],
};

export const demoRun = (): LiveRun => ({ id: 1, kind: "passage", event: "workflow_dispatch", status: "in_progress", conclusion: null, created_at: new Date(Date.now() - 4 * 60000).toISOString(), updated_at: new Date().toISOString(), url: "https://github.com", step: "Passage du bot", mainStep: { name: "Passage du bot", status: "in_progress", conclusion: null } });
