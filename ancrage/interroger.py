"""Interrogation : question → sous-graphe pondéré + référentiel épistémique + consignes pour une IA.
Contrôle : vérification d'une réponse d'IA au regard de ce même paquet."""
import re, json
from .calcul import SEUILS, _norm

def regles_ia(g, avec_apprenant=False):
    aut = g.config.get("autorite", "l'autorité")
    ref = g.config.get("exemple_reference", "")
    return [
    "Réponds uniquement à partir des éléments fournis ; n'ajoute aucune connaissance extérieure.",
    "Cite l'identifiant entre crochets après chaque affirmation, par exemple [DEF:…] ou [" + (ref or "…") + "].",
    "Préfère les éléments d'ancrage fort ; signale explicitement un élément d'ancrage faible.",
    "Un élément au statut « propose » doit être présenté comme une proposition non validée (écrire « proposé » ou « non validé »).",
    f"Quand une lecture humaine validée existe (traduction ou résumé de {aut}), c'est la référence ; une lecture produite par l'IA n'est qu'une proposition.",
    "Si la couverture est inférieure au seuil, dis clairement que la question sort du corpus validé (« hors corpus ») et n'invente rien.",
    f"Si un seul validateur est indiqué, présente la réponse comme une vue (« selon {aut}… »), non comme un savoir établi.",
    "Le champ « usage » indique ce que des apprenants ont retenu pour cette question : c'est un signal d'utilité, pas de validité ; l'ancrage et le statut restent prioritaires.",
    "Une lecture d'apprenant non validée se présente comme telle (« lecture d'un apprenant, non validée »), jamais comme la position de l'autorité.",
    ] + ([
    "Une trajectoire d'apprenant est fournie : pars de ce qu'il a déjà construit, ne réexplique pas ce qu'il a déjà retenu, et signale explicitement où ses liens divergent du socle.",
    ] if avec_apprenant else [])
MOTS_VIDES = set("que quoi qui est ce cette ces les des une un du de la le et en a au aux pour par sur dans comment pourquoi quel quelle quels quelles signifie sont qu est-ce".split())


def _mots(s):
    return {w for w in _norm(s).split() if len(w) > 3 and w not in MOTS_VIDES}


def trouver_concepts(g, question):
    """Concepts de départ : question de la banque si elle existe, sinon correspondance lexicale."""
    qn = _norm(question).strip()
    for qid in g.par_type("question"):
        e = g.E[qid]
        if _norm(e["contenu"]["texte"]).strip() == qn and g.statut(qid) != "rejete":
            return list(e["contenu"]["concepts"]), qid
    mq = _mots(question)
    sc = []
    for cid in g.par_type("concept"):
        c = g.E[cid]["contenu"]
        lab = _mots(c["libelle"] + " " + " ".join(s[1] for s in c["sens"]))
        o = len(mq & lab)
        w = _norm(c.get("wylie") or "").strip()
        bonus = 2 if (w and w in _norm(question)) else 0
        if o or bonus:
            sc.append((-(o + bonus), cid))
    sc.sort()
    return [c for _, c in sc[:5]], None


def descriptions_de_la_question(g, question, qid):
    """Descriptions d'apprenants qui répondent à cette question (même question de base ou même texte)."""
    qn = _norm(question).strip()
    out = []
    for d in g.par_type("description"):
        c = g.E[d]["contenu"]
        if (qid and c.get("qid") and "Q:" + c["qid"] == qid) or _norm(c.get("question", "")).strip() == qn:
            out.append(d)
    return out


def usage(g, descs):
    """Pour chaque élément : nombre de descriptions qui le retiennent et nombre d'apprenants."""
    n, qui = {}, {}
    for d in descs:
        for x in g.E[d]["contenu"]["elements"]:
            n[x] = n.get(x, 0) + 1
            qui.setdefault(x, set()).add(g.E[d]["prov"]["operateur"])
    return {x: {"descriptions": n[x], "apprenants": len(qui[x])} for x in n}


def trajectoire_apprenant(g, apprenant):
    """Résumé du chemin d'un apprenant : questions, éléments retenus, liens et leur situation."""
    from .vues import _comparer_relation, _lib
    uid = next((k for k, a in g.d["agents"].items() if k.startswith("utilisateur:")
                and (k == apprenant or k == "utilisateur:" + apprenant or a["nom"] == apprenant)), None)
    if not uid:
        return None
    descs = sorted((d for d in g.par_type("description") if g.E[d]["prov"]["operateur"] == uid), key=lambda d: g.E[d]["prov"]["date"] or "")
    if not descs:
        return None
    qs, cnt, liens = [], {}, {}
    for d in descs:
        c = g.E[d]["contenu"]
        if c["question"] not in qs:
            qs.append(c["question"])
        for x in c["elements"]:
            cnt[x] = cnt.get(x, 0) + 1
        for r in c["relations"]:
            liens[r] = liens.get(r, 0) + 1
    return {"apprenant": g.d["agents"][uid]["nom"], "descriptions": len(descs), "questions_posees": qs,
            "elements_deja_retenus": [{"id": x, "libelle": _lib(g, x), "fois": n, "statut": g.statut(x)}
                                      for x, n in sorted(cnt.items(), key=lambda t: -t[1]) if x in g.E][:15],
            "liens_construits": [{**{k: v for k, v in _comparer_relation(g, r).items() if k in ("vous", "autorite", "ia")}, "fois": n}
                                 for r, n in sorted(liens.items(), key=lambda t: -t[1])]}


def apprenants(g):
    return [a["nom"] for k, a in g.d["agents"].items() if k.startswith("utilisateur:")]


def interroger(g, question, apprenant=None, inclure_usage=True):
    concepts, qid = trouver_concepts(g, question)
    voisins = []
    for rid in g.par_type("relation"):
        if g.statut(rid) == "rejete":
            continue
        r = g.E[rid]["contenu"]
        if r["de"] in concepts or r["vers"] in concepts:
            voisins.append(rid)
    appuis = {}
    temoin = set(g.d.get("temoin", []))
    for p, c in g.d["mentions"]:
        if c in concepts and p not in temoin:
            appuis[p] = appuis.get(p, 0) + 1
    def poids(p):
        r = g.reference(p)
        return g.E[r or p]["ancrage"]["indice"]
    rang = sorted(appuis, key=lambda p: (-appuis[p], -poids(p)))
    elements = []
    for cid in concepts:
        elements += [cid, "DEF:" + cid[2:]]
    for p in rang[:6]:                                        # socle d'abord, avec sa lecture de référence
        elements += [p] if g.E[p]["type"] == "source" else []
        r = g.reference(p)
        elements += [r] if r else ([] if g.E[p]["type"] == "source" else [p])
    elements += voisins
    descs_q = descriptions_de_la_question(g, question, qid)
    us = usage(g, descs_q)
    for x in (sorted(us, key=lambda x: -us[x]["descriptions"])[:4] if inclure_usage else []):   # retenus par des apprenants
        if x not in elements:
            elements.append(x)
    for p in rang[:3]:                                        # propositions IA, pour comparaison
        ia = g.proposition_ia(p)
        if ia: elements.append(ia)
    elements = [e for e in dict.fromkeys(elements) if e in g.E and g.statut(e) != "rejete"][:SEUILS["elements_max"]]
    couverts = [c for c in concepts if any(cc == c and g.appui_atteste(p) for p, cc in g.d["mentions"])]
    couverture = round(len(couverts) / len(concepts), 2) if concepts else 0.0
    valideurs = sorted({v["agent"] for e in elements for v in g.validations_de(e) if g.d["agents"].get(v["agent"], {}).get("type") == "humain"})
    anc = [g.E[e]["ancrage"]["indice"] for e in elements]
    origine_ia = sum(1 for e in elements if g.agent_de(e).get("type") == "ia")
    alertes = []
    if couverture < SEUILS["couverture_min"]:
        alertes.append("couverture_faible")
    if len(valideurs) < SEUILS["validateurs_min"]:
        alertes.append("validateur_unique")
    if elements and origine_ia / len(elements) > SEUILS["alerte_part_ia"]:
        alertes.append("part_ia_elevee")
    ref = {"base": g.d["nom"], "version": g.d.get("version", ""), "question_reconnue": qid,
           "couverture": couverture, "ancrage_moyen": round(sum(anc) / len(anc), 3) if anc else 0,
           "part_origine_ia": round(origine_ia / len(elements), 2) if elements else 0,
           "validateurs": [g.d["agents"][v]["nom"] for v in valideurs], "alertes": alertes}
    els = []
    for e in elements:
        x = g.E[e]; c = x["contenu"]
        texte = c.get("texte") or c.get("libelle") or ""
        if x["type"] == "concept":
            texte = c["libelle"] + (f" ({c['tib']}, {c['wylie']})" if c.get("tib") else "")
        if x["type"] == "source":
            texte = c["titre"] + (f" – {c['auteurs']}" if c.get("auteurs") else "")
        if x["type"] == "resume":
            texte = c["texte"]
        if x["type"] == "relation":
            texte = f"{g.E[c['de']]['contenu']['libelle']} — {c['libelle']} → {g.E[c['vers']]['contenu']['libelle']}"
        ch = " ← ".join(f"{et['operation']} par {g.d['agents'].get(et['operateur'] or '', {}).get('nom', '?')}" for et in g.chaine(e) if et["type"] != "source")
        src = next((et for et in g.chaine(e) if et["type"] == "source"), None)
        vs = "; ".join(f"{g.d['agents'].get(v['agent'], {}).get('nom', v['agent'])} : {v['statut']}" for v in g.validations_de(e)) or "aucune"
        el = {"id": e, "type": x["type"], "texte": texte, "statut": g.statut(e),
              "ancrage": x["ancrage"]["indice"], "niveau": x["ancrage"]["niveau"],
              "provenance": ch + (f" ← {g.E[src['entite']]['contenu']['titre']}" if src else ""),
              "validations": vs}
        if e in us:
            el["usage"] = {"retenu_dans": us[e]["descriptions"], "apprenants": us[e]["apprenants"]}
        els.append(el)
    ref["descriptions_d_apprenants_sur_cette_question"] = len(descs_q)
    paquet = {"question": question, "referentiel": ref, "regles": regles_ia(g, apprenant is not None), "elements": els}
    if apprenant:
        t = trajectoire_apprenant(g, apprenant)
        paquet["trajectoire_apprenant"] = t if t else {"apprenant": apprenant, "descriptions": 0}
    return paquet


def consigne(paquet):
    """Texte prêt à envoyer à n'importe quelle IA."""
    return ("Tu réponds à une question à partir d'un modèle de connaissances relativisé.\n"
            "Règles :\n- " + "\n- ".join(paquet["regles"]) +
            "\n\nRéférentiel épistémique :\n" + json.dumps(paquet["referentiel"], ensure_ascii=False, indent=1) +
            "\n\nÉléments (avec statut, ancrage et provenance) :\n" + json.dumps(paquet["elements"], ensure_ascii=False, indent=1) +
            (("\n\nTrajectoire de l'apprenant qui pose la question :\n" + json.dumps(paquet["trajectoire_apprenant"], ensure_ascii=False, indent=1)) if paquet.get("trajectoire_apprenant") else "") +
            f"\n\nQuestion : {paquet['question']}\nRéponse (en français, chaque affirmation suivie de ses identifiants) :")


# ---------- contrôleur ----------
HEDGE = re.compile(r"propos|non valid|hypoth|ia\b|à confirmer", re.I)
HORS = re.compile(r"hors corpus|ne couvre pas|sort du corpus|aucun passage|pas dans les (trois )?textes", re.I)
ABST = re.compile(r"je ne peux|pas (de )?répon|ne permet pas|faute de source", re.I)
VUE = re.compile(r"selon |d'après ", re.I)


def controler(paquet, reponse):
    ids = {e["id"]: e for e in paquet["elements"]}
    phrases = [p.strip() for p in re.split(r"(?<=[.!?])\s+", reponse.strip()) if p.strip()]
    rapport, nb_ok = [], 0
    for ph in phrases:
        cites = re.findall(r"\[([^\]]+)\]", ph)
        cites = [c.strip() for x in cites for c in x.split(",")]
        pb = []
        if len(ph) > 40 and not cites and not HORS.search(ph) and not ABST.search(ph):
            pb.append("affirmation non sourcée")
        for c in cites:
            if c not in ids:
                pb.append(f"identifiant inconnu ou hors paquet : {c}")
            elif ids[c]["statut"] == "propose" and not HEDGE.search(ph):
                pb.append(f"{c} est « proposé » mais présenté comme établi")
            elif ids[c]["niveau"] == "faible" and not HEDGE.search(ph) and "faible" not in ph.lower():
                pb.append(f"{c} a un ancrage faible, non signalé")
        rapport.append({"phrase": ph, "citations": cites, "problemes": pb})
        nb_ok += not pb
    glob = []
    ref = paquet["referentiel"]
    if "couverture_faible" in ref["alertes"] and not HORS.search(reponse):
        glob.append("la couverture est faible mais la réponse ne le dit pas (« hors corpus » attendu)")
    if "validateur_unique" in ref["alertes"] and not VUE.search(reponse) and not (HORS.search(reponse) or ABST.search(reponse)):
        glob.append("validateur unique : la réponse devrait se présenter comme une vue (« selon … »)")
    taux = nb_ok / len(phrases) if phrases else 0
    verdict = "conforme" if taux == 1 and not glob else ("à reprendre" if taux >= 0.6 else "refusée")
    return {"verdict": verdict, "phrases_conformes": f"{nb_ok}/{len(phrases)}", "problemes_globaux": glob, "detail": rapport}
