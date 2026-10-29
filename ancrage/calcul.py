"""Indice d'ancrage et moniteur de boucle.

L'indice d'ancrage d'une entité mesure à quel point elle est fondée dans la
base validée, RELATIVEMENT à sa chaîne de provenance. Il n'est pas une mesure
de vérité. Il est toujours livré avec ses composantes.
"""
import json, math, os, re, unicodedata

ICI = os.path.dirname(__file__)
SEUILS = json.load(open(os.path.join(ICI, "regles", "seuils.json"), encoding="utf-8"))
OP = SEUILS["poids_operations"]


def _validation_facteur(g, eid):
    st = g.statut(eid)
    return {"valide": 1.0, "source": 1.0, "variable": 0.8, "propose": 0.55, "corriger": 0.4, "rejete": 0.0}[st], st


def _independance(g, eid):
    if g.E[eid]["type"] == "source" and not g.validations_de(eid):
        return 1.0, "texte source (socle), attribué à son auteur"
    vs = [v for v in g.validations_de(eid) if v["statut"] in ("valide", "variable")]
    if not vs:
        return 0.6, "aucune validation"
    op = g.E[eid]["prov"]["operateur"]
    tiers = [v for v in vs if v["agent"] != op and g.d["agents"].get(v["agent"], {}).get("type") == "humain"]
    if len({v["agent"] for v in tiers}) >= 2:
        return 1.0, "plusieurs validateurs tiers"
    if tiers:
        return 0.95, "validée par un tiers"
    return 0.85, "validée par son propre auteur (autorité, non indépendante)"


def _origine(g, eid, st):
    a = g.agent_de(eid)
    if a.get("type") == "ia":
        return (0.75 if st in ("valide", "variable") else 0.3), "IA" + (" validée" if st in ("valide", "variable") else " non validée")
    return 1.0, a.get("nom", "humain")


def _transformations(g, eid):
    ch = g.chaine(eid)
    f, ops = 1.0, []
    for et in ch:
        if et["type"] == "source":
            continue
        f *= OP.get(et["operation"], 0.7)
        ops.append(et["operation"])
    return f, ops, (ch[-1]["type"] == "source")


def _concordance(g, eid, cache):
    e = g.E[eid]
    t = e["type"]
    if t == "concept":
        pas = {p for p, c in g.d["mentions"] if c == eid}
        n = sum(1 for p in pas if g.appui_atteste(p)) if pas else 0
        return (1 - 0.5 ** n) if n else 0.3, f"{n} élément(s) du socle attesté(s) le mentionnent"
    if t in ("definition", "question", "relation", "description"):
        par = [p for p in e["prov"]["derive_de"] if p in g.E]
        if not par:
            return 0.3, "aucun appui"
        vals = [ancrage(g, p, cache)["indice"] for p in par]
        return sum(vals) / len(vals), f"moyenne de {len(par)} élément(s) d'appui"
    return 1.0, "texte source unique"


def ancrage(g, eid, cache=None):
    cache = {} if cache is None else cache
    if eid in cache:
        return cache[eid]
    cache[eid] = {"indice": 0.5}  # garde contre les cycles
    v, st = _validation_facteur(g, eid)
    o, o_l = _origine(g, eid, st)
    t, ops, a_source = _transformations(g, eid)
    s = 1.0 if a_source else 0.4
    i, i_l = _independance(g, eid)
    c, c_l = _concordance(g, eid, cache)
    comp = {"source": s, "transformations": t, "origine": o, "validation": v, "independance": i, "concordance": c}
    if min(comp.values()) <= 0:
        ind = 0.0
    else:
        ind = math.exp(sum(math.log(x) for x in comp.values()) / len(comp))
    plafond = ""
    if g.agent_de(eid).get("type") == "ia" and st not in ("valide", "variable") and ind > SEUILS["plafond_ia_non_validee"]:
        ind, plafond = SEUILS["plafond_ia_non_validee"], "plafonné : contenu d'IA non validé"
    niv = "fort" if ind >= SEUILS["niveau_fort"] else "moyen" if ind >= SEUILS["niveau_moyen"] else "faible"
    res = {"indice": round(ind, 3), "niveau": niv, "statut": st,
           "composantes": {k: round(x, 3) for k, x in comp.items()},
           "explications": {"origine": o_l, "transformations": " → ".join(reversed(ops)) or "aucune",
                            "independance": i_l, "concordance": c_l,
                            "source": "remonte à un texte source" if a_source else "pas de texte source",
                            **({"plafond": plafond} if plafond else {})}}
    cache[eid] = res
    return res


def tout_calculer(g):
    cache = {}
    for eid in g.E:
        g.E[eid]["ancrage"] = ancrage(g, eid, cache)
    return cache


# ---------- similarité (écart IA / référence) ----------
def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9 ]", " ", "".join(ch for ch in s if not unicodedata.combining(ch)))


def chrf(a, b, n=3):
    """F-score sur n-grammes de caractères (proche de chrF), 0 à 1."""
    def grams(s):
        s = re.sub(r"\s+", " ", _norm(s)).strip()
        return [s[i:i + n] for i in range(max(0, len(s) - n + 1))]
    A, B = grams(a), grams(b)
    if not A or not B:
        return 0.0
    from collections import Counter
    ca, cb = Counter(A), Counter(B)
    inter = sum((ca & cb).values())
    p, r = inter / len(A), inter / len(B)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def moniteur(g):
    """Indicateurs globaux de la boucle et alertes."""
    validables = [k for k, e in g.E.items() if e["type"] in ("concept", "definition", "relation", "question", "traduction")]
    valides = [k for k in validables if g.statut(k) in ("valide", "variable")]
    ia_valides = [k for k in valides if g.agent_de(k).get("type") == "ia"]
    valideurs = {v["agent"] for v in g.d["validations"] if g.d["agents"].get(v["agent"], {}).get("type") == "humain"}
    temoin = set(g.d.get("temoin", []))
    ecarts, scores_t = [], []
    for p in list(g.E):
        ia, ref = g.proposition_ia(p), g.reference(p)
        if ia and ref and g.E[ia]["type"] == "traduction":
            sim = chrf(g.E[ia]["contenu"]["texte"], g.E[ref]["contenu"]["texte"])
            (scores_t if p in temoin else ecarts).append(sim)
    rejets = sum(1 for v in g.d["validations"] if v["statut"] == "rejete")
    ind = {"entites": len(g.E), "validations": len(g.d["validations"]),
           "part_validee": round(len(valides) / max(1, len(validables)), 3),
           "part_origine_ia_dans_valide": round(len(ia_valides) / max(1, len(valides)), 3),
           "validateurs_humains": sorted(valideurs),
           "ecart_ia_reference": round(1 - sum(ecarts) / len(ecarts), 3) if ecarts else None,
           "score_temoin": round(sum(scores_t) / len(scores_t), 3) if scores_t else None,
           "taux_rejet": round(rejets / max(1, len(g.d["validations"])), 3),
           "ancrage_moyen": round(sum(e["ancrage"]["indice"] for e in g.E.values() if "ancrage" in e) / max(1, len(g.E)), 3)}
    al = []
    S = SEUILS
    if ind["part_origine_ia_dans_valide"] > S["alerte_part_ia"]:
        al.append(f"circularité : {ind['part_origine_ia_dans_valide']:.0%} du validé est d'origine IA (seuil {S['alerte_part_ia']:.0%})")
    if len(valideurs) < S["validateurs_min"]:
        al.append(f"validateur unique ({', '.join(valideurs) or 'aucun'}) : les réponses sont une vue, pas un consensus")
    if ind["score_temoin"] is not None and ind["score_temoin"] < S["temoin_min"]:
        al.append(f"jeu témoin : similarité IA/référence {ind['score_temoin']:.2f} sous le seuil {S['temoin_min']}")
    ind["alertes"] = al
    return ind
