// Test local du connecteur (Node 18+) : simule une IA qui explore le corpus puis déclare son chemin.
import fs from "fs"; import path from "path"; import url from "url";
const ici = path.dirname(url.fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(ici, "worker.js"), "utf8").replace('import CORPUS from "./corpus.json";', 'import CORPUS from "./corpus.json" with { type: "json" };');
fs.writeFileSync(path.join(ici, ".worker_test.mjs"), src);
const W = (await import(path.join(ici, ".worker_test.mjs"))).default;
const env = { JOURNAL_KEY: "test" };
let session = null, n = 0;
async function rpc(method, params) {
  const r = await W.fetch(new Request("https://x/mcp", { method: "POST", headers: { "content-type": "application/json", ...(session ? { "mcp-session-id": session } : {}) },
    body: JSON.stringify({ jsonrpc: "2.0", id: ++n, method, params }) }), env);
  session = r.headers.get("mcp-session-id"); return r.status === 202 ? null : r.json();
}
const init = await rpc("initialize", { protocolVersion: "2025-06-18", clientInfo: { name: "IA de test" }, capabilities: {} });
console.log("initialize:", init.result.serverInfo, init.result.protocolVersion);
await W.fetch(new Request("https://x/mcp", { method: "POST", headers: { "mcp-session-id": session }, body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) }), env);
console.log("outils:", (await rpc("tools/list", {})).result.tools.map(t => t.name).join(", "));
const call = (name, args) => rpc("tools/call", { name, arguments: args }).then(r => r.result.content[0].text);
console.log((await call("chercher", { mots: "décrire description relativisée" })).split("\n").slice(0, 4).join("\n"));
await call("lire_notion", { id: "n04" }); await call("lire_notion", { id: "n01" }); await call("voir_relations", { id: "n04" });
// déclaration volontairement embellie : dit avoir lu D11 et n03 sans les avoir ouverts, cite D26 jamais ouvert, omet n01
console.log(await call("declarer_chemin", { question: "Que veut dire décrire selon la MCR ?", lus: ["n04", "D11", "n03"],
  affirmations: [{ phrase: "Décrire, c'est produire une description relativisée.", appuis: ["n04"], origine: "corpus" },
                 { phrase: "Elle dépend d'une génération, d'un objet et d'une vue.", appuis: ["D26", "n03"], origine: "corpus" },
                 { phrase: "C'est une idée proche du perspectivisme.", appuis: [], origine: "savoir général" }] }));
const j = await W.fetch(new Request(`https://x/journal.json?cle=test&session=${session}`), env); const s = await j.json();
console.log(JSON.stringify(s.comparaison.ecarts, null, 1), "accord", s.comparaison.accord_declare_reel);
const p = await W.fetch(new Request(`https://x/journal?cle=test&session=${session}`), env); fs.writeFileSync("/tmp/journal_test.html", await p.text());
console.log("refus sans clé :", (await W.fetch(new Request("https://x/journal"), env)).status);
fs.unlinkSync(path.join(ici, ".worker_test.mjs"));
