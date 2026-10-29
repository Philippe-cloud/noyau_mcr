"""Adaptateur : corpus MCR (Méthode de Conceptualisation Relativisée, bibliographie D11–D61).

Entrées attendues dans <corpus>/entrees/ :
  corpus_mcr.json        documents (fiches, résumés FR/EN), concepts, relations, questions (export de l'application)
  validations/*.json     fichiers « validation-mcr-v1 » du mode Validation (Mioara)
  trajectoires/*.json    fichiers « trajectoire-mcr-v2 » des utilisateurs (facultatif) ;
                         ils peuvent contenir les retours de l'IA demandés dans l'application (« retours_ia »)
  propositions_ia/*.json fichiers « propositions-ia-mcr-v1 » : retours et propositions d'une IA (facultatif)

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
    for f in sorted(glob.glob(os.path.join(src, "trajectoires", "*.json"))):
        ajouter_trajectoire(g, json.load(open(f, encoding="utf-8")))
    for f in sorted(glob.glob(os.path.join(src, "propositions_ia", "*.json"))):
        o = json.load(open(f, encoding="utf-8"))
        if o.get("format") != "propositions-ia-mcr-v1":
            raise ValueError(f"{f} : fichier de propositions IA inconnu")
        uid = "utilisateur:" + o["apprenant"] if o.get("apprenant") else None
        for r in o.get("retours", []):
            ajouter_retour_ia(g, r, uid)
    # les validations en dernier : elles peuvent porter sur des propositions issues des retours IA
    for f in sorted(glob.glob(os.path.join(src, "validations", "*.json"))):
        appliquer_validation(g, json.load(open(f, encoding="utf-8")))
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
        eid = {"doc": "RES:", "concept": "DEF:", "rel": "R:", "q": "Q:", "pia": "PIA:"}[typ] + ref
        if eid not in g.E or not it.get("statut"):
            continue
        e = g.E[eid]
        for champ, cle in (("fr", "texte"), ("en", "texte_en"), ("def", "texte"), ("q", "texte"), ("lab", "libelle"), ("texte", "texte")):
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
    for r in t.get("retours_ia", []):
        ajouter_retour_ia(g, r, uid)


def ajouter_retour_ia(g, r, uid=None):
    """Retour d'une IA sur une plante d'un apprenant, et propositions qu'il contient.

    Le retour (RET:) dérive des descriptions de l'apprenant et des éléments cités ; chaque
    proposition (PIA:) dérive de ses appuis. Tout entre avec l'IA pour opérateur, donc au
    statut « proposé » et plafonné tant que l'autorité ne l'a pas validé (onglet « Propositions IA »).
    """
    uid = uid or "utilisateur:anonyme"
    if uid not in g.d["agents"]:
        g.agent(uid, uid.split(":", 1)[1], "humain", "apprenant")
    ok = lambda ids: [x for x in dict.fromkeys(ids) if x in g.E]
    descs = [k for k in g.E if k.startswith(f"DESC:{uid}:{r.get('plante')}:")]
    cites = [c for ph in r.get("retour", []) for c in ph.get("citations", [])]
    rid = f"RET:{uid}:{r['id']}"
    ctl = r.get("controle") or {}
    g.entite(rid, "retour", {"texte": " ".join(ph["phrase"] for ph in r.get("retour", [])), "phrases": r.get("retour", []),
                             "prochaine_question": r.get("prochaine_question", ""), "question": r.get("question", ""),
                             "qid": r.get("qid"), "destinataire": uid, "modele": r.get("modele", ""),
                             "controle": {"verdict": ctl.get("verdict"), "problemes": ctl.get("problemes", [])}},
             derive_de=ok(descs + cites), operation="retour_ia", operateur="ia", date=r.get("date"))
    if ctl.get("verdict") == "refusée":
        return  # un retour refusé par le contrôle reste tracé, mais ses propositions ne vont pas à l'autorité
    for k, p in enumerate(r.get("propositions", []), 1):
        ids = [p.get("cible"), p.get("de"), p.get("vers")] + list(p.get("concepts", [])) + list(p.get("appuis", []))
        g.entite(f"PIA:{r['id']}-{k}", "proposition",
                 {"nature": p.get("nature", "autre"), "texte": p.get("texte", ""), "cible": p.get("cible"),
                  "de": p.get("de"), "vers": p.get("vers"), "concepts": p.get("concepts", []), "appuis": p.get("appuis", []),
                  "justification": p.get("justification", ""), "issue_du_retour": rid, "verdict_controle": ctl.get("verdict"),
                  "problemes_controle": [x for x in ctl.get("problemes", []) if x.startswith(f"proposition {k}")]},
                 derive_de=ok([x for x in ids if x]) or [rid], operation="proposition_ia", operateur="ia", date=r.get("date"))
