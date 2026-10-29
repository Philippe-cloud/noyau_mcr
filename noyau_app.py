"""Application de bureau du noyau d'ancrage.

Lance un petit serveur local (127.0.0.1) et ouvre l'interface dans le navigateur.
Les données de travail sont copiées au premier lancement dans Documents/NoyauAncrage
(corpus, applications) : on y dépose validations et trajectoires, on y retrouve les sorties.

  NoyauAncrage.exe            ouvre l'interface
  NoyauAncrage.exe --test     exécute une boucle sans interface (vérification)
"""
import sys, os, io, json, shutil, threading, webbrowser, glob, contextlib, traceback, re, urllib.parse, socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from ancrage import cli as CLI, interroger as Q, calcul      # noqa: E402
from ancrage.graphe import Graphe                                   # noqa: E402

CORPUS = {"mcr": "MCR (Mioara Mugur-Schächter)"}
DOSSIER = os.environ.get("NOYAU_DONNEES") or os.path.join(os.path.expanduser("~"), "Documents", "NoyauAncrage")


def preparer_donnees():
    """Copie le corpus et les applications livrés, sans écraser ce qui existe."""
    for sous in ("corpus", "applications"):
        src = os.path.join(BASE, sous)
        for racine, dirs, fichiers in os.walk(src):
            rel = os.path.relpath(racine, src)
            if any(p in ("versions", "sorties") for p in rel.split(os.sep)):
                continue
            dest = os.path.join(DOSSIER, sous, rel)
            os.makedirs(dest, exist_ok=True)
            if os.path.basename(rel) in ("validations", "trajectoires"):
                continue                       # jamais de validations ou trajectoires d'exemple dans les données réelles
            for f in fichiers:
                if not os.path.exists(os.path.join(dest, f)):
                    shutil.copy2(os.path.join(racine, f), os.path.join(dest, f))
    for c in CORPUS:
        for s in ("validations", "trajectoires"):
            os.makedirs(os.path.join(DOSSIER, "corpus", c, "entrees", s), exist_ok=True)


def chemin_corpus(c):
    if c not in CORPUS:
        raise ValueError("corpus inconnu")
    return os.path.join(DOSSIER, "corpus", c)


def capturer(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a)
    return buf.getvalue()


def derniere(c):
    vs = sorted(glob.glob(os.path.join(chemin_corpus(c), "versions", "*.graphe.json")))
    return Graphe.charger(vs[-1]) if vs else None


def sorties(c):
    ds = sorted(glob.glob(os.path.join(chemin_corpus(c), "sorties", "*")))
    if not ds:
        return None
    d = ds[-1]
    return {"version": os.path.basename(d), "fichiers": sorted(os.listdir(d)), "dossier": d}


def entrees(c):
    e = os.path.join(chemin_corpus(c), "entrees")
    return {s: sorted(os.listdir(os.path.join(e, s))) for s in ("validations", "trajectoires")}


# ------------------------------------------------------------------ API
def api(route, q, corps):
    c = (corps or {}).get("corpus") or q.get("corpus", ["mcr"])[0]
    if route == "/api/info":
        return {"dossier": DOSSIER, "corpus": CORPUS}
    if route == "/api/etat":
        g = derniere(c)
        return {"corpus": c, "entrees": entrees(c), "sorties": sorties(c),
                "version": g.d.get("version") if g else None, "moniteur": g.d.get("moniteur") if g else None,
                "shacl": g.d.get("shacl") if g else None, "apprenants": Q.apprenants(g) if g else []}
    if route == "/api/ajouter":
        typ = corps["type"]
        if typ not in ("validations", "trajectoires"):
            raise ValueError("type inconnu")
        nom = re.sub(r"[^\w.\-]+", "_", os.path.basename(corps["nom"]))
        o = json.loads(corps["contenu"])
        attendu = {"validations": "validation-", "trajectoires": "trajectoire-"}[typ]
        fmt = o.get("format", "")
        if not fmt.startswith(attendu) or not fmt.endswith("mcr-v1" if typ == "validations" else "mcr-v2"):
            raise ValueError(f"Ce fichier n'est pas une {typ[:-1]} du corpus {CORPUS[c]} (format « {fmt or 'absent'} »).")
        with open(os.path.join(chemin_corpus(c), "entrees", typ, nom), "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, indent=1)
        return {"ok": True, "nom": nom, "entrees": entrees(c)}
    if route == "/api/retirer":
        typ = corps["type"]; nom = os.path.basename(corps["nom"])
        p = os.path.join(chemin_corpus(c), "entrees", typ, nom)
        if typ in ("validations", "trajectoires") and os.path.exists(p):
            os.remove(p)
        return {"ok": True, "entrees": entrees(c)}
    if route == "/api/boucle":
        cwd = os.getcwd()
        try:
            os.chdir(DOSSIER)
            journal = capturer(CLI.main, ["boucle", os.path.join("corpus", c)])
        finally:
            os.chdir(cwd)
        return {"journal": journal, "sorties": sorties(c)}
    if route == "/api/comparer":
        cwd = os.getcwd()
        try:
            os.chdir(DOSSIER)
            journal = capturer(CLI.main, ["comparer", os.path.join("corpus", c)])
        finally:
            os.chdir(cwd)
        return {"journal": journal}
    if route == "/api/consigne":
        g = derniere(c)
        if not g:
            raise ValueError("Lancez d'abord la boucle.")
        p = Q.interroger(g, corps["question"], corps.get("apprenant") or None)
        return {"referentiel": p["referentiel"], "elements": p["elements"], "trajectoire": p.get("trajectoire_apprenant"),
                "consigne": Q.consigne(p)}
    if route == "/api/controler":
        g = derniere(c)
        if not g:
            raise ValueError("Lancez d'abord la boucle.")
        return Q.controler(Q.interroger(g, corps["question"], corps.get("apprenant") or None), corps["reponse"])
    if route == "/api/vue":
        s = sorties(c)
        nom = q.get("nom", [""])[0]
        if not s or nom not in s["fichiers"] or not nom.endswith(".json"):
            raise ValueError("vue introuvable")
        return json.load(open(os.path.join(s["dossier"], nom), encoding="utf-8"))
    if route == "/api/ouvrir-dossier":
        d = (sorties(c) or {}).get("dossier") or chemin_corpus(c)
        if sys.platform.startswith("win"):
            os.startfile(d)  # noqa
        elif sys.platform == "darwin":
            os.system(f'open "{d}"')
        else:
            os.system(f'xdg-open "{d}" >/dev/null 2>&1 &')
        return {"ok": True, "dossier": d}
    raise KeyError(route)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _envoyer(self, code, corps, ctype="application/json; charset=utf-8", nom=None):
        b = corps if isinstance(corps, bytes) else json.dumps(corps, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        if nom:
            self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        self.end_headers()
        self.wfile.write(b)

    def _route(self, corps=None):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._envoyer(200, open(os.path.join(BASE, "interface", "index.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path == "/fichier":
                c, nom = q["corpus"][0], os.path.basename(q["nom"][0])
                s = sorties(c)
                if not s or nom not in s["fichiers"]:
                    return self._envoyer(404, {"erreur": "fichier introuvable"})
                p = os.path.join(s["dossier"], nom)
                ct = "text/html; charset=utf-8" if nom.endswith(".html") else "application/json; charset=utf-8"
                return self._envoyer(200, open(p, "rb").read(), ct, None if q.get("voir") else nom)
            if u.path == "/api/quitter":
                self._envoyer(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self._envoyer(200, api(u.path, q, corps))
        except KeyError:
            return self._envoyer(404, {"erreur": "inconnu"})
        except Exception as e:
            traceback.print_exc()
            return self._envoyer(400, {"erreur": str(e)})

    def do_GET(self):
        self._route()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            corps = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return self._envoyer(400, {"erreur": "requête illisible"})
        self._route(corps)


def port_libre(depart=8765):
    for p in range(depart, depart + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)):
                return p
    raise RuntimeError("aucun port libre")


def main():
    for flux in (sys.stdout, sys.stderr):            # console Windows : éviter les erreurs d'encodage (é, →…)
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    preparer_donnees()
    if "--test" in sys.argv:
        for c in CORPUS:
            print(api("/api/boucle", {}, {"corpus": c})["journal"])
        return
    port = port_libre()
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Noyau d'ancrage : {url}\nDonnées : {DOSSIER}\nFermez cette fenêtre ou cliquez « Quitter » dans l'interface pour arrêter.")
    if "--sans-navigateur" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
