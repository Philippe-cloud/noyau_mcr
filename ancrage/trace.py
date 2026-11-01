"""Protocole de trace commun (« trace-v1 ») : une même grammaire pour l'autorité, l'apprenant et l'IA.

Chaque trace décrit un ou plusieurs chemins vers une question :
  recherches    ce que l'acteur a consulté, retenu ou écarté (avec la raison), dans l'ordre réel
  etapes        les étapes du chemin (descriptions, validations, raisonnement), chacune avec ses appuis ;
                nature « sourcee » ou « savoir_propre » (apport de l'auteur, lecture personnelle, savoir interne d'une IA)
  relations     les liens établis, avec leur origine : « base » (relation de la base), « indexation »
                (rejoint l'indexation d'un document par la base) ou « propre » (lecture personnelle)
  affirmations  ce que l'acteur affirme ou sait expliquer, chaque phrase avec ses appuis

Le savoir propre n'a pas le même statut selon l'acteur : contribution fondatrice pour l'autorité,
vue légitime pour l'apprenant, part non vérifiable pour l'IA. Le plafond d'ancrage ne vaut que pour l'IA.
"""
import json, os, re

FORMAT = "trace-v1"
LOT = "traces-v1"


def _base(g):
    return {"corpus": g.d["nom"], "version": g.d.get("version")}


def depuis_validations(g):
    """Trajectoire fondatrice : la suite datée des actes de validation de l'autorité."""
    vs = sorted([v for v in g.d["validations"] if g.d["agents"].get(v["agent"], {}).get("type") == "humain"],
                key=lambda v: v.get("date") or "")
    if not vs:
        return None
    nom = g.d["agents"][vs[0]["agent"]]["nom"]
    verbe = {"valide": "valide", "corriger": "demande la correction de", "rejete": "rejette", "variable": "admet comme variable", "propose": "laisse en proposition"}
    etapes, affs, rels = [], [], []
    for k, v in enumerate(vs, 1):
        e = g.E[v["entite"]]; c = e["contenu"]
        lib = c.get("libelle") or c.get("texte", "")[:80] or v["entite"]
        corrige = bool(e.get("original"))
        etapes.append({"n": k, "date": v.get("date"), "nature": "savoir_propre" if corrige else "sourcee",
                       "texte": f"{verbe.get(v['statut'], v['statut'])} {v['entite']} ({lib})" + (" en le reformulant" if corrige else "")
                                + (f" – « {v['commentaire']} »" if v.get("commentaire") else ""),
                       "appuis": [v["entite"]]})
        if v["statut"] in ("valide", "variable"):
            if e["type"] == "relation":
                rels.append({"de": c["de"], "vers": c["vers"], "type": c["libelle"], "origine": "base", "statut": v["statut"]})
            elif c.get("texte"):
                affs.append({"phrase": c["texte"], "appuis": [v["entite"]] + e["prov"]["derive_de"][:1]})
    return {"format": FORMAT, "acteur": {"role": "autorite", "nom": nom}, "base": _base(g),
            "chemins": [{"id": "fondateur", "question": "Établir le socle", "recherches": [], "etapes": etapes,
                         "relations": rels, "affirmations": affs}]}


def depuis_trajectoire(g, t):
    """Trace d'un apprenant à partir d'un fichier « trajectoire-mcr-v2 »."""
    rel_base = {(r["contenu"]["de"], r["contenu"]["vers"]) for k, r in g.E.items() if k.startswith("R:")}
    index = {(a, b) for a, b in g.d["mentions"]}

    def origine(A, B):
        if (A, B) in rel_base or (B, A) in rel_base: return "base"
        if (A, B) in index or (B, A) in index: return "indexation"
        return "propre"
    eid = lambda x: ("C:" if ("C:" + x) in g.E else "S:") + x
    chemins = []
    for p in t["plantes"]:
        ev = [x for x in t.get("traces", []) if x.get("plante") == p["id"]]
        rech, n = [], 0
        for x in ev:
            if x.get("type") in ("consulter", "retenir", "lacher", "ecarter") and x.get("el"):
                n += 1
                it = {"n": n, "moment": x["date"], "action": {"consulter": "consultation", "retenir": "retenu", "lacher": "lâché", "ecarter": "écarté"}[x["type"]],
                      "objet": eid(x["el"])}
                if x["type"] == "retenir": it["retenues"] = [eid(x["el"])]
                if x.get("via"): it["via"] = x["via"]
                if x["type"] in ("lacher", "ecarter"):
                    it["rejetees"] = [{"id": eid(x["el"]), "raison": x.get("raison") or "écarté par l'apprenant (sans raison donnée)"}]
                rech.append(it)
        ds = p["descriptions"]
        etapes = [{"n": d["n"], "date": d["date"], "nature": "sourcee",
                   "texte": f"Description D{d['n']} : {len(d['c'])} concept(s), {len(d['d'])} document(s), {len(d['r'])} relation(s)",
                   "appuis": ["C:" + x for x in d["c"]] + ["S:" + x for x in d["d"]]} for d in ds]
        rels = []
        if ds:
            for s in ds[-1]["r"]:
                a, ty, b = s.split("|")
                A, B = eid(a), eid(b)
                rels.append({"de": A, "vers": B, "type": ty, "origine": origine(A, B)})
        affs = [{"phrase": d["explication"], "description": f"D{d['n']}", "appuis": ["C:" + x for x in d["c"]] + ["S:" + x for x in d["d"]]}
                for d in ds if d.get("explication")]
        retires = [{"moment": x["date"], "de": eid(x["a"]), "vers": eid(x["b"]), "type": x.get("rtype", "")} for x in ev if x.get("type") == "delier"]
        chemins.append({"id": p["id"], "question": p["question"], "qid": p.get("qid"), "recherches": rech,
                        "etapes": etapes, "relations": rels, "affirmations": affs, **({"liens_retires": retires} if retires else {})})
    return {"format": FORMAT, "acteur": {"role": "apprenant", "nom": t.get("apprenant") or "apprenant anonyme"},
            "base": _base(g), "chemins": chemins}


def vers_trajectoire_ia(trace, chemin):
    """Convertit le chemin d'une trace d'IA en « trajectoire-ia-v1 » pour l'audit."""
    ch = chemin
    rel = [{"de": r["de"], "vers": r["vers"], "type": r.get("type", ""), "appuis": r.get("appuis", [])} for r in ch.get("relations", [])]
    etapes = [{"texte": e.get("texte", ""), "appuis": e.get("appuis", []),
               **({"nature": "savoir_interne"} if e.get("nature") == "savoir_propre" else {})} for e in ch.get("etapes", [])]
    return {"format": "trajectoire-ia-v1", "question": ch.get("question", ""), "modele": trace["acteur"].get("nom", "IA"),
            "date": trace.get("date"), "raisonnement": etapes, "relations": rel, "sources_externes": trace.get("sources_externes", []),
            "recherches": [{"requete": r.get("objet", ""), "moment": r.get("moment", ""), "retenues": [], "rejetees":
                            [{"titre": x.get("id", ""), "raison": x.get("raison", "")} for x in r.get("rejetees", [])]} for r in ch.get("recherches", [])],
            "reponse": [{"phrase": a.get("phrase", ""), "appuis": a.get("appuis", [])} for a in ch.get("affirmations", [])]}


def traces_ia(lot):
    """Liste des (trace, chemin) d'IA contenus dans un lot « traces-v1 » ou une trace isolée."""
    ts = lot["traces"] if lot.get("format") == LOT else [lot]
    return [(t, c) for t in ts if t.get("format") == FORMAT and t["acteur"]["role"] == "ia" for c in t.get("chemins", [])]


def exporter(g, dossier, sortie):
    """Écrit les traces de l'autorité et des apprenants (protocole commun) dans le dossier de sortie."""
    fs = []
    a = depuis_validations(g)
    if a:
        json.dump(a, open(os.path.join(sortie, "trace_autorite.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        fs.append("trace_autorite.json")
    for f in sorted(os.listdir(os.path.join(dossier, "entrees", "trajectoires"))) if os.path.isdir(os.path.join(dossier, "entrees", "trajectoires")) else []:
        if not f.endswith(".json"):
            continue
        t = json.load(open(os.path.join(dossier, "entrees", "trajectoires", f), encoding="utf-8"))
        if t.get("format") != "trajectoire-mcr-v2":
            continue
        nom = "trace_apprenant_" + re.sub(r"\.json$", "", f) + ".json"
        json.dump(depuis_trajectoire(g, t), open(os.path.join(sortie, nom), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        fs.append(nom)
    return fs
