"""Régénération des applications HTML à partir de la dernière version du modèle.

L'interface (applications/<corpus>/app.html) ne change pas. Le noyau y injecte :
  - les données de l'application, enrichies de l'indice d'ancrage et de la genèse de chaque élément ;
  - les validations consolidées de l'autorité (format du mode Validation), qui s'affichent pour tous.
"""
import json, os
from .vues import genese_lisible

CLE_APP = {"mcr": {"format": "validation-mcr-v1", "fichier": "corpus_mcr.json", "valideur": "Mioara Mugur-Schächter"}}
ROLES_FICHIER = ("validateur", "validatrice (autorité)")


def _an(g, eid):
    if eid not in g.E:
        return None
    a = g.E[eid]["ancrage"]
    return {"indice": a["indice"], "niveau": a["niveau"], "statut": g.statut(eid), "genese": genese_lisible(g, eid)}


def validations_consolidees(g, nom):
    cfg = CLE_APP[nom]
    items, valideur = {}, cfg["valideur"]
    for v in g.d["validations"]:
        if v["role"] not in ROLES_FICHIER:
            continue
        eid = v["entite"]; e = g.E[eid]; pre, ref = eid.split(":", 1)
        cle = {"DEF": "concept", "R": "rel", "Q": "q", "RES": "doc", "PIA": "pia"}.get(pre)
        if not cle:
            continue
        valideur = g.d["agents"][v["agent"]]["nom"]
        it = {"statut": v["statut"], "commentaire": v["commentaire"], "date": v["date"]}
        if e.get("original"):
            for k in e["original"]:
                champ = {("DEF", "texte"): "def", ("Q", "texte"): "q", ("R", "libelle"): "lab", ("RES", "texte"): "fr", ("RES", "texte_en"): "en", ("PIA", "texte"): "texte"}.get((pre, k))
                if champ: it[champ] = e["contenu"][k]
        if pre == "DEF" and g.E["C:" + ref].get("original", {}).get("libelle"):
            it["lab"] = g.E["C:" + ref]["contenu"]["libelle"]
        prev = items.get(f"{cle}:{ref}")
        if not prev or (v["date"] or "") >= (prev["date"] or ""):
            items[f"{cle}:{ref}"] = it
    return {"format": cfg["format"], "valideur": valideur, "items": items, "types": None,
            "source": f"noyau, version {g.d.get('version')}"}


def regenerer(g, dossier):
    nom = os.path.basename(os.path.normpath(dossier))
    racine = os.path.dirname(os.path.dirname(os.path.normpath(os.path.abspath(dossier))))
    tpl = open(os.path.join(racine, "applications", nom, "app.html"), encoding="utf-8").read()
    data = json.load(open(os.path.join(dossier, "entrees", CLE_APP[nom]["fichier"]), encoding="utf-8"))
    for c in data["concepts"]:
        c["noyau"] = _an(g, "C:" + c["id"]); c["noyau_def"] = _an(g, "DEF:" + c["id"])
    for d in data["docs"]:
        d["noyau"] = _an(g, "S:" + d["id"]); d["noyau_resume"] = _an(g, "RES:" + d["id"])
    for r in data["relations"]:
        r["noyau"] = _an(g, f"R:{r['a']}|{r['b']}")
    for q in data["questions"]:
        q["noyau"] = _an(g, "Q:" + q["id"])
    from .vues import _prop
    data["propositionsIA"] = []
    for p in g.par_type("proposition"):
        x = _prop(g, p); c = g.E[p]["contenu"]
        x.update(id=p.split(":", 1)[1], texte_propose=g.E[p].get("original", {}).get("texte", x["texte"]), date=g.E[p]["prov"]["date"], destinataire_anonyme=True,
                 retour=g.E[c["issue_du_retour"]]["contenu"]["question"] if c["issue_du_retour"] in g.E else "")
        data["propositionsIA"].append(x)
    m = g.d.get("moniteur", {})
    data["noyau"] = {"version": g.d.get("version"), "alertes": m.get("alertes", []), "ancrage_moyen": m.get("ancrage_moyen"),
                     "part_validee": m.get("part_validee")}
    val = validations_consolidees(g, nom)
    dj = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    vj = json.dumps(val, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace("__DATA__", dj).replace("__VAL__", vj)
    out = os.path.join(dossier, "sorties", g.d["version"])
    os.makedirs(out, exist_ok=True)
    chemin = os.path.join(out, "explorer_mcr.html")
    open(chemin, "w", encoding="utf-8").write(html)
    json.dump(val, open(os.path.join(out, f"validations_consolidees_{nom}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return chemin
