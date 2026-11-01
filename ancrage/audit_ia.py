"""Audit d'une réponse d'IA : cas d'usage séparé de la boucle du corpus.

Une IA répond à une question et déclare sa trajectoire (format « trajectoire-ia-v1 ») :
les éléments du corpus qu'elle mobilise, les sources externes qu'elle cite, les relations
qu'elle établit, les étapes de son raisonnement et les affirmations de sa réponse.

Cette trajectoire passe par le même moteur de règles que le reste (graphe de genèse,
règles de forme SHACL, indice d'ancrage, contrôle des statuts), mais sur une COPIE du
graphe : un audit ne modifie jamais la base, ne compte pas dans le moniteur de boucle et
ne produit aucune proposition pour l'autorité. Il produit un rapport, lisible et vérifiable.

Limite assumée : le raisonnement déclaré par l'IA est la description qu'elle en donne,
pas son fonctionnement interne. Il est traité comme sa trajectoire déclarée, une vue.
"""
import copy, html, json, os, re, datetime
from . import calcul, rdf, interroger as Q
from .vues import genese_lisible

FORMAT = "trajectoire-ia-v1"
INTERNE = re.compile(r"mes connaissances|savoir interne|non vérifi|inférence|hypoth|de ma part|je suppose|incertain", re.I)
EXTERNE = re.compile(r"externe|hors (du )?socle|hors corpus|selon |d'après ", re.I)


def _lib(g, eid):
    c = g.E[eid]["contenu"]
    if eid.startswith("ETP:"):
        return ("savoir interne · " if c.get("savoir_interne") else "") + f"étape {eid[4:]} : {c['texte'][:70]}"
    if g.E[eid]["type"] == "relation" and c.get("de") in g.E and c.get("vers") in g.E:
        return f"{_lib(g, c['de'])} → {_lib(g, c['vers'])} ({c.get('libelle', '')})"
    return c.get("libelle") or c.get("titre") or (c.get("texte") or eid)[:90]


def _genese(g, eid):
    return re.sub(r"([^←()]{70})[^←()]*\(", r"\1… (", genese_lisible(g, eid))


def graphe_vide():
    from .graphe import Graphe
    g = Graphe("sans corpus")
    g.d["config"] = {"autorite": None}
    return g


def _court(x, n=110):
    x = " ".join(str(x).split())
    return x if len(x) <= n else x[:n].rsplit(" ", 1)[0] + "…"


def genese_courante(g, fid, reformulations, trouve_par, vu=None):
    """La genèse d'une affirmation racontée en phrases simples."""
    vu = vu if vu is not None else set()
    phrases = []
    for x in g.E[fid]["prov"]["derive_de"]:
        if x in vu:
            continue
        vu.add(x)
        e = g.E[x]; c = e["contenu"]
        if x.startswith("ETP:"):
            if c.get("savoir_interne"):
                phrases.append(f"Elle repose sur ce que l'IA sait de son entraînement, sans vérification (étape {x[4:]} : « {_court(c['texte'])} »).")
            else:
                phrases.append(f"Elle prolonge l'étape {x[4:]} du raisonnement : « {_court(c['texte'])} ».")
        elif x.startswith("RIA:"):
            phrases.append(f"Elle s'appuie sur un rapprochement fait par l'IA : « {_lib(g, c['de'])} » {c['libelle']} « {_lib(g, c['vers'])} ».")
            phrases += genese_courante(g, x, reformulations, trouve_par, vu)
        elif e["type"] == "source":
            d = f"Elle s'appuie sur « {_court(c['titre'], 90)} » ({c.get('auteurs', '')}{', ' + c['date'] if c.get('date') else ''})"
            if x in trouve_par:
                d += f", trouvé par la recherche n° {trouve_par[x][0]} (« {trouve_par[x][1]} »)"
            d += "."
            if reformulations.get(x):
                d += f" Ce que dit la source, reformulé par l'IA : {reformulations[x]}"
            phrases.append(d)
        else:
            phrases.append(f"Elle s'appuie sur « {_court(_lib(g, x), 90)} » ({g.statut(x)}).")
    return phrases


def auditer(g0, t, sans_corpus=False):
    """Retourne le rapport d'audit d'une trajectoire d'IA, sans toucher au graphe g0.

    Mode sans corpus : aucun socle validé ; les sources consultées (avec lien) tiennent lieu de
    socle provisoire, sans validation d'autorité. Les étapes « savoir_interne » déclarent ce que
    l'IA avance à partir de son seul entraînement, sans source.
    """
    if t.get("format") != FORMAT:
        raise ValueError(f"format attendu : {FORMAT}")
    g = copy.deepcopy(g0)
    aid = "ia_auditee"
    g.agent(aid, t.get("modele") or "IA auditée", "ia", "répond à une question (audit)")
    date = t.get("date") or datetime.datetime.now().isoformat(timespec="seconds")
    problemes, avert = [], []

    # sources externes déclarées
    ext = {}
    for i, s in enumerate(t.get("sources_externes", []), 1):
        sid = s.get("id") or f"EXT:{i}"
        sid = sid if sid.startswith("EXT:") else "EXT:" + sid
        auteur = s.get("auteur") or "auteur non précisé"
        xa = "externe:" + re.sub(r"\W+", "_", auteur.lower())
        if xa not in g.d["agents"]:
            g.agent(xa, auteur, "humain", "auteur d'une source externe citée par l'IA")
        g.entite(sid, "source", {"titre": s.get("titre", "(sans titre)"), "auteurs": auteur, "date": s.get("date", ""),
                                 "lien": s.get("lien", ""), "consultee_le": s.get("consultee_le", ""), "langue": "fr",
                                 "externe": not (sans_corpus and s.get("lien"))},
                 operation="creation", operateur=xa, date="")
        ext[s.get("id") or sid] = sid; ext[sid] = sid
        if not (s.get("lien") or s.get("reference")):
            avert.append(f"{sid} : source externe sans lien ni référence vérifiable")

    def resoudre(ids, locaux):
        ok, inconnus = [], []
        for x in ids or []:
            x = str(x).strip()
            y = ext.get(x) or locaux.get(x) or (x if x in g.E else None)
            (ok if y else inconnus).append(y or x)
        return list(dict.fromkeys(ok)), inconnus

    # recherches effectuées, dans l'ordre réel
    rech = t.get("recherches", [])
    trouve_par = {}
    for k, q in enumerate(rech, 1):
        for x in q.get("retenues", []):
            trouve_par.setdefault(ext.get(x, x), (k, q.get("requete", "")))
    for sid in [x for x in g.E if x.startswith("EXT:")]:
        if rech and sid not in trouve_par:
            avert.append(f"{sid} : source dont la recherche d'origine n'est pas déclarée")

    # relations établies par l'IA
    locaux = {}
    for k, r in enumerate(t.get("relations", []), 1):
        ap, inc = resoudre(r.get("appuis"), locaux)
        de, vers = ext.get(r.get("de"), r.get("de")), ext.get(r.get("vers"), r.get("vers"))
        if de not in g.E or vers not in g.E:
            problemes.append(f"relation {k} : élément inconnu ({r.get('de')} → {r.get('vers')})"); continue
        rid = f"RIA:{k}"
        g.entite(rid, "relation", {"de": de, "vers": vers, "libelle": r.get("type") or r.get("libelle", "")},
                 derive_de=list(dict.fromkeys([de, vers] + ap)), operation="inference", operateur=aid, date=date)
        locaux[f"R{k}"] = rid; locaux[rid] = rid
        problemes += [f"relation {k} : appui inconnu {x}" for x in inc]

    # étapes du raisonnement déclaré
    etapes = []
    for k, e in enumerate(t.get("raisonnement", []), 1):
        ap, inc = resoudre(e.get("appuis"), locaux)
        eid = f"ETP:{k}"
        interne = e.get("nature") == "savoir_interne"
        g.entite(eid, "etape_ia", {"texte": e.get("texte", ""), "savoir_interne": interne}, derive_de=ap,
                 operation="raisonnement_ia", operateur=aid, date=date)
        locaux[f"E{k}"] = eid; locaux[eid] = eid
        etapes.append(eid)
        problemes += [f"étape {k} : appui inconnu {x}" for x in inc]
        if interne:
            avert.append(f"étape {k} : savoir interne du modèle, déclaré comme non sourcé")
        elif not ap:
            avert.append(f"étape {k} sans appui : elle ne repose que sur l'IA")

    # affirmations de la réponse
    affs, reformul = [], {}
    for k, a in enumerate(t.get("reponse", []), 1):
        ph = a.get("phrase", "").strip()
        ap, inc = resoudre(a.get("appuis"), locaux)
        fid = f"AFF:{k}"
        g.entite(fid, "affirmation", {"texte": ph}, derive_de=ap, operation="affirmation_ia", operateur=aid, date=date)
        pb = [f"appui inconnu {x}" for x in inc]
        if not ap and len(ph) > 40 and not Q.HORS.search(ph) and not Q.ABST.search(ph):
            pb.append("affirmation non sourcée")
        for x in ap:
            st = g.statut(x)
            if g.E[x]["contenu"].get("externe") and not EXTERNE.search(ph):
                pb.append(f"{x} est une source externe non attestée, non signalée comme telle")
            elif st == "propose" and not Q.HEDGE.search(ph) and not x.startswith(("ETP:", "RIA:", "EXT:")):
                pb.append(f"{x} est « proposé » mais présenté comme établi")
            elif st == "rejete":
                pb.append(f"{x} a été rejeté par l'autorité")
        affs.append((fid, ph, ap, pb))
        refs = {ext.get(k, k): v for k, v in (a.get("ce_que_dit_la_source") or {}).items()}
        for x in ap:
            if g.E[x]["type"] == "source" and x not in refs:
                avert.append(f"affirmation {k} : ce que dit {x} n'est pas précisé")
        reformul[fid] = refs

    # moteur de règles : ancrage puis formes SHACL, sur la copie
    calcul.tout_calculer(g)
    for eid in g.E:
        if g.E[eid]["contenu"].get("externe"):
            a = g.E[eid]["ancrage"]
            if a["indice"] > calcul.SEUILS["plafond_ia_non_validee"]:
                a["indice"] = calcul.SEUILS["plafond_ia_non_validee"]; a["niveau"] = "faible"
                a["explications"]["plafond"] = "plafonné : source externe citée par l'IA, non attestée dans le socle"
    # recalcul des éléments qui dépendent des sources externes plafonnées
    cache = {k: g.E[k]["ancrage"] for k in g.E if g.E[k]["contenu"].get("externe")}
    for eid in [x for x in g.E if x.startswith(("RIA:", "ETP:", "AFF:"))]:
        g.E[eid]["ancrage"] = calcul.ancrage(g, eid, cache)
    ok, viol = rdf.verifier(rdf.vers_rdf(g))
    nouveaux = ("EXT", "RIA", "ETP", "AFF")
    viol = [v for v in viol if any(f"/{n}%3A" in v["noeud"] for n in nouveaux)]

    def el(x):
        e = g.E[x]
        return {"id": x, "libelle": _lib(g, x), "type": e["type"], "statut": g.statut(x),
                "ancrage": e["ancrage"]["indice"], "niveau": e["ancrage"]["niveau"],
                "externe": bool(e["contenu"].get("externe"))}

    appuis = {x for _, _, ap, _ in affs for x in ap}
    base = [x for x in appuis if not x.startswith(nouveaux)]

    def racines(x, vu=None):
        vu = vu if vu is not None else set()
        if x in vu: return set()
        vu.add(x)
        e = g.E[x]
        if e["type"] == "source": return {"source"}
        if e["contenu"].get("savoir_interne"): return {"interne"}
        par = e["prov"]["derive_de"]
        return set().union(*[racines(p, vu) for p in par]) if par else {"rien"}
    seul_interne = 0
    for fid, ph, ap, pb in affs:
        if ap and "source" not in racines(fid):
            seul_interne += 1
            if not INTERNE.search(ph):
                pb.append("repose sur le seul savoir interne du modèle sans le signaler")
    lignes, nb_ok = [], 0
    for fid, ph, ap, pb in affs:
        a = g.E[fid]["ancrage"]
        cp = [v for v in a["composantes"].values()]
        brut = round(__import__("math").prod(cp) ** (1 / len(cp)), 3) if cp and min(cp) > 0 else 0
        lignes.append({"id": fid, "phrase": ph, "ancrage": a["indice"], "ancrage_avant_plafond": brut, "niveau": a["niveau"],
                       "composantes": a["composantes"], "explications": a["explications"],
                       "genese": _genese(g, fid), "genese_courante": genese_courante(g, fid, reformul.get(fid, {}), trouve_par),
                       "appuis": [el(x) for x in ap], "problemes": pb})
        nb_ok += not pb
    taux = nb_ok / len(affs) if affs else 0
    verdict = "conforme" if taux == 1 and not problemes and not viol else ("à reprendre" if taux >= 0.6 else "refusée")
    moy = round(sum(l["ancrage"] for l in lignes) / len(lignes), 3) if lignes else 0
    return {"format": "audit-ia-v1", "question": t.get("question", ""), "modele": t.get("modele", ""), "date": date,
            "corpus": g0.d["nom"], "version_du_modele": g0.d.get("version"),
            "verdict": verdict, "affirmations_conformes": f"{nb_ok}/{len(affs)}",
            "mode": "sans corpus" if sans_corpus else "corpus",
            "synthese": {"ancrage_moyen": moy,
                         "affirmations_sans_aucune_source": seul_interne,
                         "etapes_de_savoir_interne": sum(1 for e in etapes if g.E[e]["contenu"].get("savoir_interne")),
                         "appuis_dans_la_base": len(base),
                         "dont_valides": sum(1 for x in base if g.statut(x) in ("valide", "variable")),
                         "dont_sources_du_socle": sum(1 for x in base if g.E[x]["type"] == "source"),
                         "sources_externes": len([x for x in g.E if x.startswith("EXT:")]),
                         "etapes_de_raisonnement": len(etapes),
                         "affirmations_sans_appui_de_la_base": sum(1 for _, _, ap, _ in affs if not [x for x in ap if not x.startswith(nouveaux)])},
            "problemes": problemes, "avertissements": avert,
            "regles_de_forme": {"conforme": not viol, "violations": viol},
            "affirmations": lignes,
            "recherches": [{"n": k, "requete": q.get("requete", ""), "moment": q.get("moment", ""), "pourquoi": q.get("pourquoi", ""),
                            "retenues": [{"id": ext.get(x, x), "titre": g.E[ext.get(x, x)]["contenu"]["titre"]} for x in q.get("retenues", []) if ext.get(x, x) in g.E],
                            "rejetees": q.get("rejetees", [])} for k, q in enumerate(rech, 1)],
            "ordre_du_chemin": t.get("ordre_du_chemin", ""),
            "raisonnement_declare": [{"id": e, "texte": g.E[e]["contenu"]["texte"], "appuis": [el(x) for x in g.E[e]["prov"]["derive_de"]],
                                      "ancrage": g.E[e]["ancrage"]["indice"]} for e in etapes],
            "sources_externes": [el(x) | {"lien": g.E[x]["contenu"].get("lien", "")} for x in g.E if x.startswith("EXT:")],
            "limite": "Le raisonnement déclaré est la description que l'IA donne de son chemin, pas son fonctionnement interne : "
                      "il est audité comme sa trajectoire déclarée. L'audit ne modifie pas la base et ne produit aucune validation."}


def consigne(g, question):
    """Consigne à donner à une IA pour qu'elle réponde en déclarant sa trajectoire."""
    p = Q.interroger(g, question)
    gabarit = {"format": FORMAT, "question": question, "modele": "nom du modèle",
               "raisonnement": [{"texte": "étape de raisonnement", "appuis": ["C:…", "S:…"]}],
               "relations": [{"de": "C:…", "vers": "C:…", "type": "libellé", "appuis": ["S:…"]}],
               "sources_externes": [{"id": "EXT:1", "titre": "…", "auteur": "…", "date": "…", "lien": "…"}],
               "reponse": [{"phrase": "affirmation", "appuis": ["C:…", "E1", "EXT:1"]}]}
    return ("Tu réponds à une question en déclarant ta trajectoire : les éléments que tu mobilises, ton raisonnement par étapes, "
            "les relations que tu établis et les affirmations de ta réponse, chacune avec ses appuis.\n"
            "Règles :\n- " + "\n- ".join(p["regles"]) +
            "\n- Tu peux citer une source extérieure au corpus : déclare-la dans « sources_externes » et signale-la dans la phrase (« source externe »)."
            "\n- Les appuis d'une affirmation peuvent être des identifiants du corpus, une étape (E1, E2…), une relation (R1…) ou une source externe (EXT:…)."
            "\n\nÉléments du corpus (avec statut, ancrage et provenance) :\n" + json.dumps(p["elements"], ensure_ascii=False, indent=1) +
            f"\n\nQuestion : {question}\n\nRéponds UNIQUEMENT par un JSON de cette forme :\n" + json.dumps(gabarit, ensure_ascii=False, indent=1))


def rapport_html(r):
    e = lambda s: html.escape(str(s if s is not None else ""))
    col = {"fort": "#15803d", "moyen": "#b45309", "faible": "#b91c1c"}
    vcol = {"conforme": "#15803d", "à reprendre": "#b45309", "refusée": "#b91c1c"}
    s = r["synthese"]
    def ap(a):
        tag = "source externe" if a["externe"] else "source consultée" if a["type"] == "source" else "raisonnement de l'IA" if a["type"] == "etape_ia" else "relation établie par l'IA" if a["id"].startswith("RIA:") else a["statut"]
        return f"<span class='ap' title='{e(a['id'])}'>{e(a['libelle'][:70])} <i>({e(tag)}, {a['ancrage']})</i></span>"
    def ligne(l):
        pbs = "".join("<div class='pb'>⚠ " + e(p) + "</div>" for p in l["problemes"])
        aps = "".join(ap(a) for a in l["appuis"]) or "<i>aucun appui</i>"
        gc = "".join("<li>" + e(x) + "</li>" for x in l.get("genese_courante", []))
        return ("<tr><td><b>" + e(l["phrase"]) + "</b><ul class='gc'>" + gc + "</ul>"
                "<details class='gen'><summary>chaîne technique</summary>" + e(l["genese"]) + "</details>" + pbs + "</td>"
                "<td class='c'><b style='color:" + col[l["niveau"]] + "'>" + str(l["ancrage"]) + "</b><br><small>" + l["niveau"] + "</small>"
                + ("<br><small title='indice sans le plafond appliqué aux contenus d’IA non validés'>sans plafond : " + str(l["ancrage_avant_plafond"]) + "</small>" if l["ancrage_avant_plafond"] > l["ancrage"] else "") + "</td>"
                "<td>" + aps + "</td></tr>")
    rows = "".join(ligne(l) for l in r["affirmations"])
    def rech(q):
        ret = "".join("<li>✔ " + e(x["titre"]) + "</li>" for x in q["retenues"]) or "<li><i>aucune retenue</i></li>"
        rej = "".join("<li>✘ " + e(x.get("titre", "")) + " — <i>" + e(x.get("raison", "")) + "</i></li>" for x in q["rejetees"])
        return ("<div class='rq'><b>Recherche " + str(q["n"]) + "</b> · « " + e(q["requete"]) + " »" + (" · " + e(q["moment"]) if q["moment"] else "")
                + ("<div class='pq'>" + e(q["pourquoi"]) + "</div>" if q["pourquoi"] else "") + "<ul>" + ret + rej + "</ul></div>")
    chemin = "".join(rech(q) for q in r.get("recherches", []))
    if r.get("mode") == "sans corpus":
        nsrc = len(r["sources_externes"])
        synth = (f"<ul><li>Mode <b>sans corpus</b> : aucune autorité n'a validé de socle ; les sources consultées tiennent lieu de socle provisoire.</li>"
                 f"<li>Sources consultées : {nsrc} · étapes de raisonnement déclarées : {s['etapes_de_raisonnement']}, dont {s['etapes_de_savoir_interne']} de savoir interne</li>"
                 f"<li>Affirmations qui ne remontent à aucune source : {s['affirmations_sans_aucune_source']}</li></ul>")
    else:
        synth = (f"<ul><li>Appuis pris dans la base : {s['appuis_dans_la_base']} (dont {s['dont_valides']} validés, {s['dont_sources_du_socle']} textes du socle)</li>"
                 f"<li>Sources externes citées : {s['sources_externes']} · étapes de raisonnement déclarées : {s['etapes_de_raisonnement']}</li>"
                 f"<li>Affirmations sans aucun appui dans la base : {s['affirmations_sans_appui_de_la_base']}</li></ul>")
    etapes = "".join(f"<li>{e(x['texte'])} <small>— appuis : {', '.join(e(a['libelle'][:50]) for a in x['appuis']) or 'aucun'}</small></li>" for x in r["raisonnement_declare"])
    ext = "".join(f"<li>{e(x['libelle'])} {('— ' + e(x['lien'])) if x['lien'] else '— <i>sans lien</i>'}</li>" for x in r["sources_externes"])
    pbs = "".join(f"<li>{e(p)}</li>" for p in r["problemes"] + r["avertissements"] + [f"forme : {v['message']}" for v in r["regles_de_forme"]["violations"]]) or "<li>Aucun.</li>"
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Audit d'une réponse d'IA</title>
<style>body{{font:15px/1.5 Georgia,serif;color:#1f2328;max-width:960px;margin:30px auto;padding:0 18px}}h1{{font-size:23px;margin:0}}
h2{{font-size:17px;color:#1f3864;border-bottom:1px solid #dce3ee;padding-bottom:3px;margin-top:26px}}.sous{{color:#6b7280;font-style:italic}}
.v{{display:inline-block;padding:3px 10px;border-radius:10px;color:#fff;background:{vcol[r['verdict']]}}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border-bottom:1px solid #e5e7eb;padding:7px;vertical-align:top;text-align:left}}th{{background:#f3f6fb}}
.c{{text-align:center;white-space:nowrap}}.ap{{display:block;margin:2px 0}}.gen{{color:#6b7280;font-size:12.5px;margin-top:4px}}.pb{{color:#b91c1c;font-size:13px}}
.gc{{margin:4px 0 2px 18px;padding:0;font-size:13.5px;color:#374151}}.gc li{{margin:2px 0}}.gen summary{{cursor:pointer;color:#6b7280;font-size:12px}}
.rq{{border:1px solid #e5e7eb;border-radius:8px;padding:8px 12px;margin:8px 0;font-size:14px}}.rq ul{{margin:4px 0 0 0;padding-left:18px}}.pq{{color:#4b5563;font-size:13.5px;font-style:italic}}
.lim{{background:#f3f6fb;border-left:4px solid #2e5597;padding:8px 12px;font-size:14px}}</style></head><body>
<h1>Audit d'une réponse d'IA</h1>
<p class="sous">{e(r['modele'])} · {e(r['date'])} · {e(r['corpus'])}{(', version ' + e(r['version_du_modele'])) if r['version_du_modele'] else ''}</p>
<p><b>Question :</b> {e(r['question'])}</p>
<p><span class="v">{e(r['verdict'])}</span> &nbsp; {e(r['affirmations_conformes'])} affirmations conformes · ancrage moyen <b>{s['ancrage_moyen']}</b></p>
{synth}
{("<h2>Mon chemin, dans l'ordre réel</h2><p class='pq'>" + e(r.get("ordre_du_chemin", "")) + "</p>" + chemin) if chemin else ""}
<h2>Comment j'ai construit la réponse</h2><ol>{etapes or '<li>Aucun.</li>'}</ol>
<h2>Affirmations</h2><p style="font-size:13.5px;color:#4b5563">Tant qu'aucun humain n'a validé une affirmation d'IA, son ancrage est plafonné à 0,5. L'indice « sans plafond » montre ce que vaudrait son chemin de sources s'il était validé : il permet de distinguer une affirmation bien sourcée d'une affirmation qui ne repose que sur l'IA.</p><table><tr><th>Affirmation et sa genèse</th><th>Ancrage</th><th>Appuis</th></tr>{rows}</table>
<h2>{'Sources consultées' if r.get('mode') == 'sans corpus' else 'Sources externes'}</h2><ul>{ext or '<li>Aucune.</li>'}</ul>
<h2>Points relevés</h2><ul>{pbs}</ul>
<p class="lim">{e(r['limite'])}</p></body></html>"""


def executer(g, chemin, dossier_corpus, sans_corpus=False):
    t = json.load(open(chemin, encoding="utf-8"))
    r = auditer(g, t, sans_corpus)
    nom = os.path.splitext(os.path.basename(chemin))[0]
    out = os.path.join(dossier_corpus, "audits_ia", "sorties", f"{datetime.datetime.now():%Y%m%d-%H%M%S}_{nom}")
    os.makedirs(out, exist_ok=True)
    json.dump(r, open(os.path.join(out, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out, "audit.html"), "w", encoding="utf-8").write(rapport_html(r))
    return r, out
