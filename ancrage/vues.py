"""Vues : projections du modèle pour chaque acteur.

  vue_autorite   socle documenté, règles proposées à confirmer, divergences (agrégées, anonymes)
  vue_ia         écarts avec la référence, tendances, corrections reçues, alertes (sans le jeu témoin)
  trajectoires   trajectoire de chaque apprenant, enrichie (indices, comparaison des trois vues)
  moniteur       indicateurs de la boucle

Chaque vue cite la version du modèle et les identifiants des éléments : on peut remonter à la genèse.
"""
import json, os, glob, re
from collections import Counter, defaultdict
from .calcul import chrf, _norm


def _nom(g, aid):
    return g.d["agents"].get(aid, {}).get("nom", aid)


def genese_lisible(g, eid):
    parts = []
    for et in g.chaine(eid):
        e = g.E[et["entite"]]
        if et["type"] == "source":
            parts.append(f"{e['contenu']['titre']} ({_nom(g, et['operateur'])})")
        else:
            parts.append(f"{et['operation']} par {_nom(g, et['operateur'])}")
    return " ← ".join(parts)


def temoignages(g, eid):
    return [{"par": _nom(g, v["agent"]), "role": v["role"], "statut": v["statut"], "date": v["date"],
             "commentaire": v["commentaire"]} for v in g.validations_de(eid)]


def _humain_valideur(g, v):
    return g.d["agents"].get(v["agent"], {}).get("type") == "humain"


# ---------------------------------------------------------------- autorité
def regles_terminologiques(g):
    """Correspondances terme → traduction attestées dans au moins deux lectures de référence."""
    out = []
    for cid in g.par_type("concept"):
        c = g.E[cid]["contenu"]
        if not c.get("sens"):
            continue
        appuis = [p for p, cc in g.d["mentions"] if cc == cid]
        refs = {p: g.reference(p) for p in appuis}
        for s in c["sens"]:
            for var in [v.strip() for v in re.split(r";|,", s[1]) if len(v.strip()) > 3]:
                vn = _norm(re.sub(r"\(.*?\)", "", var)).strip()
                if len(vn) < 4:
                    continue
                att = [p for p, r in refs.items() if r and vn in _norm(g.E[r]["contenu"]["texte"])]
                if len(att) >= 2:
                    out.append({"terme": cid, "tib": c.get("tib", ""), "wylie": c.get("wylie", ""), "traduction": var,
                                "attestations": [g.reference(p) for p in att], "nb": len(att),
                                "statut_actuel": c.get("statut_glossaire"),
                                "proposition": f"traduire {c.get('wylie') or c['libelle']} par « {var} »",
                                "a_confirmer": c.get("statut_glossaire") != "confirmé"})
    return sorted(out, key=lambda r: (-r["a_confirmer"], -r["nb"]))


def relations_suggerees(g, seuil=3):
    """Paires de concepts souvent mentionnées ensemble dans le socle, sans relation dans la base."""
    par = defaultdict(set)
    for p, c in g.d["mentions"]:
        par[p].add(c)
    co = Counter()
    for cs in par.values():
        cs = sorted(cs)
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                co[(cs[i], cs[j])] += 1
    existe = {(g.E[r]["contenu"]["de"], g.E[r]["contenu"]["vers"]) for r in g.par_type("relation")}
    existe |= {(b, a) for a, b in existe}
    return [{"de": a, "vers": b, "libelles": [g.E[a]["contenu"]["libelle"], g.E[b]["contenu"]["libelle"]],
             "co_mentions": n, "proposition": "qualifier la relation entre ces deux notions"}
            for (a, b), n in co.most_common(40) if n >= seuil and (a, b) not in existe][:15]


def relations_apprenants(g):
    """Relations créées par les apprenants, absentes de la base (agrégées, sans noms)."""
    cnt, qui = Counter(), defaultdict(set)
    for d in g.par_type("description"):
        e = g.E[d]
        for r in e["contenu"]["relations"]:
            a, t, b = r.split("|")
            cnt[(a, t, b)] += 1
            qui[(a, t, b)].add(e["prov"]["operateur"])
    out = []
    for (a, t, b), n in cnt.most_common():
        ra, rb = f"R:{a}|{b}", f"R:{b}|{a}"
        base = ra if ra in g.E else rb if rb in g.E else None
        out.append({"de": "C:" + a, "type": t, "vers": "C:" + b, "descriptions": n, "apprenants": len(qui[(a, t, b)]),
                    "dans_la_base": base, "libelle_base": g.E[base]["contenu"]["libelle"] if base else None,
                    "statut_base": g.statut(base) if base else None})
    return out


def vue_autorite(g):
    socle = []
    for eid, e in g.E.items():
        if e["type"] == "source" or (e["type"] == "passage" and g.statut(eid) == "valide"):
            r = g.reference(eid)
            socle.append({"id": eid, "type": e["type"], "titre": e["contenu"].get("titre") or e["contenu"].get("texte", "")[:80],
                          "lecture_de_reference": r, "genese": genese_lisible(g, r or eid), "temoignages": temoignages(g, r or eid)})
    a_traiter = Counter(); attente = []
    for eid, e in g.E.items():
        if g.agent_de(eid).get("type") == "ia" and g.statut(eid) == "propose":
            a_traiter[e["type"]] += 1
            attente.append(eid)
    corrections = [{"id": eid, "statut": g.statut(eid), "original": e["original"], "corrige": {k: e["contenu"][k] for k in e["original"]},
                    "par": _nom(g, e.get("corrige_par", ""))} for eid, e in g.E.items() if e.get("original")]
    ecarts = []
    for p in list(g.E):
        ia, ref = g.proposition_ia(p), g.reference(p)
        if ia and ref and g.E[ia]["type"] == "traduction":
            ecarts.append({"passage": p, "reference": ref, "ia": ia, "similarite": round(chrf(g.E[ia]["contenu"]["texte"], g.E[ref]["contenu"]["texte"]), 3)})
    ecarts.sort(key=lambda x: x["similarite"])
    faibles = Counter()
    for d in g.par_type("description"):
        for x in g.E[d]["contenu"]["elements"]:
            if x in g.E and g.E[x].get("ancrage", {}).get("niveau") == "faible":
                faibles[x] += 1
    return {"vue": "autorite", "corpus": g.d["nom"], "version": g.d.get("version"), "autorite": g.config.get("autorite"),
            "socle": {"nombre": len(socle), "elements": socle},
            "a_traiter": {"par_type": dict(a_traiter), "identifiants": attente},
            "regles_proposees": {"terminologie": regles_terminologiques(g), "relations_a_qualifier": relations_suggerees(g),
                                 "relations_des_apprenants": relations_apprenants(g)},
            "corrections_faites": corrections,
            "divergences": {"ia_vs_reference_les_plus_fortes": ecarts[:8],
                            "elements_faiblement_ancres_retenus_par_les_apprenants": [{"id": k, "descriptions": n} for k, n in faibles.most_common(10)],
                            "nombre_apprenants": len({g.E[d]["prov"]["operateur"] for d in g.par_type("description")})}}


# ---------------------------------------------------------------- IA
def tendances_terminologiques(g):
    """Termes que la référence rend par une traduction attestée et que l'IA rend autrement."""
    out = []
    for r in regles_terminologiques(g):
        vn = _norm(re.sub(r"\(.*?\)", "", r["traduction"])).strip()
        manque = []
        for ref in r["attestations"]:
            p = g.E[ref]["prov"]["derive_de"][0]
            if p in g.d.get("temoin", []):
                continue
            ia = g.proposition_ia(p)
            if ia and vn not in _norm(g.E[ia]["contenu"]["texte"]):
                manque.append(ia)
        if manque:
            out.append({"terme": r["terme"], "wylie": r["wylie"], "traduction_de_reference": r["traduction"],
                        "ecarts": len(manque), "sur": len(r["attestations"]), "exemples": manque[:3]})
    return sorted(out, key=lambda x: -x["ecarts"])


def vue_ia(g):
    temoin = set(g.d.get("temoin", []))
    ecarts = []
    for p in list(g.E):
        if p in temoin:
            continue
        ia, ref = g.proposition_ia(p), g.reference(p)
        if ia and ref and g.E[ia]["type"] == "traduction":
            ecarts.append({"passage": p, "similarite_avec_reference": round(chrf(g.E[ia]["contenu"]["texte"], g.E[ref]["contenu"]["texte"]), 3)})
    retours = []
    for eid, e in g.E.items():
        if g.agent_de(eid).get("type") != "ia":
            continue
        vs = [v for v in g.validations_de(eid) if _humain_valideur(g, v) and v["statut"] in ("corriger", "rejete", "valide")]
        for v in vs:
            retours.append({"id": eid, "statut": v["statut"], "par": _nom(g, v["agent"]), "commentaire": v["commentaire"],
                            **({"ma_proposition": e["original"], "version_corrigee": {k: e["contenu"][k] for k in e["original"]}} if e.get("original") else {})})
    m = g.d.get("moniteur", {})
    return {"vue": "ia", "corpus": g.d["nom"], "version": g.d.get("version"),
            "statut_de_cette_vue": "témoin de comparaison, jamais socle d'autorité",
            "ma_trajectoire": {"ecart_moyen_avec_reference": m.get("ecart_ia_reference"), "score_jeu_temoin": m.get("score_temoin"),
                               "jeu_temoin": "contenu non communiqué", "par_passage": sorted(ecarts, key=lambda x: x["similarite_avec_reference"])},
            "mes_tendances": tendances_terminologiques(g),
            "retours_des_validateurs": retours,
            "alertes": m.get("alertes", []),
            "consigne": "Signale dans tes réponses les termes où tu t'écartes habituellement de la référence ; tes productions restent des propositions tant qu'un humain ne les a pas validées."}


# ---------------------------------------------------------------- apprenants
def _comparer_relation(g, r):
    a, t, b = r.split("|")
    ca, cb = "C:" + a, "C:" + b
    base = next((x for x in (f"R:{a}|{b}", f"R:{b}|{a}") if x in g.E), None)
    out = {"relation": r, "vous": f"{g.E[ca]['contenu']['libelle']} — {t} → {g.E[cb]['contenu']['libelle']}" if ca in g.E and cb in g.E else r}
    socle = [p for p in {p for p, c in g.d["mentions"] if c == ca} & {p for p, c in g.d["mentions"] if c == cb} if g.appui_atteste(p)]
    out["autorite"] = (f"{g.config.get('autorite')} réunit ces deux notions dans {len(socle)} élément(s) du socle : " + ", ".join(sorted(socle)[:5])) if socle else "aucun élément du socle ne réunit ces deux notions"
    if base:
        st = g.statut(base); lab = g.E[base]["contenu"]["libelle"]
        out["base"] = {"id": base, "libelle": lab, "statut": st}
        out["ia"] = f"l'IA proposait « {lab} »" + (" (validé)" if st == "valide" else " (non validé)" if st == "propose" else f" ({st})")
        out["accord"] = (_norm(lab) == _norm(t))
    else:
        out["ia"] = "l'IA ne proposait pas de relation entre ces notions"
    return out


def trajectoires_enrichies(g, dossier):
    sorties = []
    for f in sorted(glob.glob(os.path.join(dossier, "entrees", "trajectoires", "*.json"))):
        t = json.load(open(f, encoding="utf-8"))
        uid = "utilisateur:" + (t.get("apprenant") or "anonyme")
        enr = {"version_modele": g.d.get("version"), "descriptions": {}}
        for p in t["plantes"]:
            for d in p["descriptions"]:
                did = f"DESC:{uid}:{p['id']}:D{d['n']}"
                if did not in g.E:
                    continue
                e = g.E[did]
                enr["descriptions"][f"{p['id']}-D{d['n']}"] = {
                    "ancrage": e["ancrage"], "elements": [{"id": x, "statut": g.statut(x), "ancrage": g.E[x]["ancrage"]["indice"],
                                                          "niveau": g.E[x]["ancrage"]["niveau"]} for x in e["contenu"]["elements"]],
                    "relations": [_comparer_relation(g, r) for r in d["r"]]}
        t["noyau"] = enr
        sorties.append((os.path.basename(f).replace(".json", "_enrichie.json"), t))
    return sorties


def exporter(g, dossier):
    out = os.path.join(dossier, "sorties", g.d["version"])
    os.makedirs(out, exist_ok=True)
    nom = os.path.basename(os.path.normpath(dossier))
    fichiers = {f"vue_autorite_{nom}.json": vue_autorite(g), f"vue_ia_{nom}.json": vue_ia(g),
                f"moniteur_{nom}.json": {"version": g.d["version"], **g.d["moniteur"], "shacl": g.d.get("shacl")}}
    for n, t in trajectoires_enrichies(g, dossier):
        fichiers[n] = t
    for n, o in fichiers.items():
        json.dump(o, open(os.path.join(out, n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out, list(fichiers)
