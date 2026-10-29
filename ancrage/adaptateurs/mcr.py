"""Adaptateur : corpus MCR (Méthode de Conceptualisation Relativisée, bibliographie D11–D61).

Entrées attendues dans <corpus>/entrees/ :
  corpus_mcr.json        documents (fiches, résumés FR/EN), concepts, relations, questions (export de l'application)
  validations/*.json     fichiers « validation-mcr-v1 » du mode Validation (Mioara)
  trajectoires/*.json    fichiers « trajectoire-mcr-v2 » des utilisateurs (facultatif)

Socle : les documents eux-mêmes (textes des auteurs). Les résumés, définitions,
relations et questions sont des lectures produites par l'IA, à valider par Mioara.
"""
import json, glob, os, re
from ..graphe import Graphe

OP_RESUME = {"TI": "resume", "RE": "resume", "NO": "resume_notice"}


def _aid(nom):
    return "auteur:" + re.sub(r"[^a-z0-9]+", "_", nom.lower()).strip("_")


def ingerer(dossier):
    src = os.path.join(dossier, "entrees")
    data = json.load(open(os.path.join(src, "corpus_mcr.json"), encoding="utf-8"))
    g = Graphe("corpus MCR")
    g.d["config"] = {"autorite": "Mioara Mugur-Schächter", "exemple_reference": "S:D11",
                     "format_validation": "validation-mcr-v1", "format_trajectoire": "trajectoire-mcr-v2", "prefixe_doc": "S:"}
    g.agent("projet", "Équipe projet", "humain", "éditeur du corpus")
    g.agent("mioara", "Mioara Mugur-Schächter", "humain", "autorité : auteure de la MCR")
    g.agent("ia", "IA (Claude)", "ia", "résumés, définitions, relations et questions proposés")
    for d in data["docs"]:
        auteurs = d.get("auteurs") or []
        nom = auteurs[0] if auteurs else "Auteur non précisé"
        aid = "mioara" if "Mugur" in nom else _aid(nom)
        if aid not in g.d["agents"]:
            g.agent(aid, nom.replace(" (dir.)", ""), "humain", "auteur")
        g.entite("S:" + d["id"], "source", {"titre": d["titre"], "auteurs": ", ".join(auteurs), "date": d.get("date", ""),
                                           "type_doc": d.get("type", ""), "lien": d.get("lien", ""), "langue": "fr"},
                 operation="creation", operateur=aid, date="")
        g.entite("RES:" + d["id"], "resume", {"texte": d["fr"], "texte_en": d["en"], "langue": "fr",
                                             "base": {"TI": "texte intégral", "RE": "résumé auteur/éditeur", "NO": "notice seule"}[d["src"]]},
                 derive_de=["S:" + d["id"]], operation=OP_RESUME[d["src"]], operateur="ia")
    for c in data["concepts"]:
        cid = "C:" + c["id"]
        g.entite(cid, "concept", {"libelle": c["lab"], "categorie": c["type"], "reperes": c.get("refs", []),
                                  "sens": [], "statut_glossaire": "proposé"},
                 derive_de=["S:D11"], operation="extraction", operateur="ia")
        g.entite("DEF:" + c["id"], "definition", {"texte": c["def"]}, derive_de=[cid], operation="redaction", operateur="ia")
    for d in data["docs"]:
        for c in d.get("concepts", []):
            if "C:" + c in g.E:
                g.mention("S:" + d["id"], "C:" + c)
    for r in data["relations"]:
        g.entite(f"R:{r['a']}|{r['b']}", "relation", {"de": "C:" + r["a"], "vers": "C:" + r["b"], "libelle": r["lab"]},
                 derive_de=["C:" + r["a"], "C:" + r["b"]], operation="inference", operateur="ia")
    for q in data["questions"]:
        g.entite("Q:" + q["id"], "question", {"texte": q["q"], "niveau": q["niveau"], "concepts": ["C:" + c for c in q["concepts"]]},
                 derive_de=["C:" + q["concepts"][0]], operation="redaction", operateur="ia")
    for f in sorted(glob.glob(os.path.join(src, "validations", "*.json"))):
        appliquer_validation(g, json.load(open(f, encoding="utf-8")))
    for f in sorted(glob.glob(os.path.join(src, "trajectoires", "*.json"))):
        ajouter_trajectoire(g, json.load(open(f, encoding="utf-8")))
    return g


def appliquer_validation(g, v):
    if v.get("format") != "validation-mcr-v1":
        raise ValueError("fichier de validation inconnu")
    nom = v.get("valideur") or "Mioara Mugur-Schächter"
    aid = "mioara" if "mugur" in nom.lower() or "mioara" in nom.lower() else "valideur:" + re.sub(r"\W+", "_", nom.lower())
    if aid not in g.d["agents"]:
        g.agent(aid, nom, "humain", "validateur")
    for k, it in v["items"].items():
        typ, ref = k.split(":", 1)
        eid = {"doc": "RES:", "concept": "DEF:", "rel": "R:", "q": "Q:"}[typ] + ref
        if eid not in g.E or not it.get("statut"):
            continue
        e = g.E[eid]
        for champ, cle in (("fr", "texte"), ("en", "texte_en"), ("def", "texte"), ("q", "texte"), ("lab", "libelle")):
            if it.get(champ) and cle in e["contenu"] and it[champ] != e["contenu"][cle]:
                e.setdefault("original", {})[cle] = e["contenu"][cle]
                e["contenu"][cle] = it[champ]; e["corrige_par"] = aid
        g.valider(eid, aid, it["statut"], role="validatrice (autorité)", date=it.get("date"), commentaire=it.get("commentaire", ""))
        if typ == "concept" and it["statut"] in ("valide", "rejete"):
            g.valider("C:" + ref, aid, it["statut"], role="validation du terme avec son explication", date=it.get("date"))


def ajouter_trajectoire(g, t):
    if t.get("format") != "trajectoire-mcr-v2":
        raise ValueError("fichier de trajectoire inconnu")
    uid = "utilisateur:" + (t.get("apprenant") or "anonyme")
    if uid not in g.d["agents"]:
        g.agent(uid, t.get("apprenant") or "Utilisateur anonyme", "humain", "apprenant")
    for p in t["plantes"]:
        for d in p["descriptions"]:
            els = [x for x in ["C:" + x for x in d["c"]] + ["S:" + x for x in d["d"]] if x in g.E]
            g.entite(f"DESC:{uid}:{p['id']}:D{d['n']}", "description",
                     {"question": p["question"], "qid": p.get("qid"), "elements": els, "relations": d["r"], "pourquoi": d.get("pourquoi", "")},
                     derive_de=els, operation="selection", operateur=uid, date=d["date"])
