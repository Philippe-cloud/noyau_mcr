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
    """Relations créées par les apprenants (agrégées, sans noms), comparées à la base."""
    cnt, qui = Counter(), defaultdict(set)
    for d in g.par_type("description"):
        e = g.E[d]
        for r in e["contenu"]["relations"]:
            cnt[r] += 1
            qui[r].add(e["prov"]["operateur"])
    out = []
    for r, n in cnt.most_common():
        cmp = _comparer_relation(g, r)
        out.append({"relation": cmp["vous"], "descriptions": n, "apprenants": len(qui[r]),
                    "autorite": cmp.get("autorite"), "ia": cmp.get("ia"), "accord": cmp.get("accord")})
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
def _resoudre(g, x):
    """Identifiant d'application → entité du graphe (concept ou document du socle)."""
    for pre in ("C:", g.config.get("prefixe_doc", "S:"), "S:", "P:"):
        if pre + x in g.E:
            return pre + x
    return None


def _lib(g, eid):
    c = g.E[eid]["contenu"]
    return c.get("libelle") or (eid.split(":", 1)[1] + " · " + c.get("titre", "")[:60] if c.get("titre") else eid)


def _comparer_relation(g, r):
    a, t, b = r.split("|")
    ea, eb = _resoudre(g, a), _resoudre(g, b)
    out = {"relation": r, "vous": f"{_lib(g, ea) if ea else a} — {t} → {_lib(g, eb) if eb else b}"}
    aut = g.config.get("autorite")
    if not ea or not eb:
        out["autorite"] = "élément inconnu de la base"; out["ia"] = "—"; return out
    concepts = [x for x in (ea, eb) if g.E[x]["type"] == "concept"]
    autres = [x for x in (ea, eb) if g.E[x]["type"] != "concept"]
    if len(concepts) == 2:
        socle = [p for p in {p for p, c in g.d["mentions"] if c == ea} & {p for p, c in g.d["mentions"] if c == eb} if g.appui_atteste(p)]
        out["autorite"] = (f"{aut} réunit ces deux notions dans {len(socle)} élément(s) du socle : " + ", ".join(sorted(socle)[:5])) if socle else "aucun élément du socle ne réunit ces deux notions"
        base = next((x for x in (f"R:{a}|{b}", f"R:{b}|{a}") if x in g.E), None)
        if base:
            st = g.statut(base); lab = g.E[base]["contenu"]["libelle"]
            out["base"] = {"id": base, "libelle": lab, "statut": st}
            out["ia"] = f"l'IA proposait « {lab} »" + (" (validé)" if st == "valide" else " (non validé)" if st == "propose" else f" ({st})")
            out["accord"] = _norm(lab) == _norm(t)
        else:
            out["ia"] = "l'IA ne proposait pas de relation entre ces notions"
    elif len(concepts) == 1 and autres:
        doc, c = autres[0], concepts[0]
        mention = [doc, c] in g.d["mentions"] or (doc, c) in [tuple(m) for m in g.d["mentions"]]
        out["autorite"] = (f"la base indexe {doc} sur cette notion (indexation du projet, pas encore validée par {aut})" if mention
                           else f"la base n'indexe pas {doc} sur cette notion : c'est votre lecture propre")
        out["ia"] = "l'indexation proposée rejoint votre lien" if mention else "aucune indexation proposée ne fait ce lien"
        out["accord"] = mention
    else:
        out["autorite"] = "relation entre deux documents : le socle ne les relie pas directement"
        out["ia"] = "—"
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
    fiche = f"fiche_autorite_{nom}.html"
    open(os.path.join(out, fiche), "w", encoding="utf-8").write(fiche_autorite_html(g, fichiers[f"vue_autorite_{nom}.json"]))
    return out, list(fichiers) + [fiche]


# ---------------------------------------------------------------- fiche lisible pour l'autorité
def fiche_autorite_html(g, v):
    import html as H
    e = lambda s: H.escape(str(s if s is not None else ""))
    aut = v.get("autorite") or "l'autorité"
    m = g.d.get("moniteur", {})
    R = v["regles_proposees"]
    noms = {"resume": "résumés", "definition": "définitions", "concept": "concepts", "relation": "relations",
            "question": "questions", "traduction": "traductions"}
    at = ", ".join(f"{n} {noms.get(k, k)}" for k, n in v["a_traiter"]["par_type"].items()) or "rien"
    def table(entetes, lignes):
        if not lignes:
            return "<p class='vide'>Rien pour l'instant.</p>"
        return ("<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in entetes) + "</tr>" +
                "".join("<tr>" + "".join(f"<td>{c}</td>" for c in l) + "</tr>" for l in lignes) + "</table>")
    app = R["relations_des_apprenants"]
    lignes_app = [[e(r["relation"]), f"{r['apprenants']} apprenant(s), {r['descriptions']} description(s)", e(r["autorite"])] for r in app]
    lignes_rel = [[e(" / ".join(r["libelles"])), f"{r['co_mentions']} document(s)"] for r in R["relations_a_qualifier"]]
    lignes_term = [[e(r["proposition"]), str(r["nb"]), e(r["statut_actuel"])] for r in R.get("terminologie", [])[:20]]
    lignes_cor = [[e(c["id"]), e(c["statut"]), e(" ; ".join(f"{k} : « {str(x)[:120]} »" for k, x in c["original"].items())),
                   e(" ; ".join(f"« {str(x)[:120]} »" for x in c["corrige"].values()))] for c in v["corrections_faites"]]
    div = v["divergences"]["ia_vs_reference_les_plus_fortes"]
    lignes_div = [[e(d["passage"]), str(d["similarite"])] for d in div]
    faibles = [[e(x["id"] + " · " + _lib(g, x["id"]) if x["id"] in g.E else x["id"]), str(x["descriptions"])] for x in v["divergences"]["elements_faiblement_ancres_retenus_par_les_apprenants"]]
    alertes = "".join(f"<li>{e(a)}</li>" for a in m.get("alertes", [])) or "<li>Aucune.</li>"
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Fiche pour {e(aut)} – {e(v['corpus'])}</title>
<style>body{{font:15px/1.55 Georgia,'Times New Roman',serif;color:#1f2328;max-width:900px;margin:30px auto;padding:0 20px}}
h1{{font-size:24px;margin:0}}h2{{font-size:18px;margin:28px 0 6px;color:#1f3864;border-bottom:1px solid #dce3ee;padding-bottom:4px}}
.sous{{color:#6b7280;font-style:italic;margin:4px 0 18px}}.intro{{background:#f3f6fb;border-left:4px solid #2e5597;padding:10px 14px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0}}th,td{{border-bottom:1px solid #e5e7eb;padding:6px;text-align:left;vertical-align:top}}th{{background:#f3f6fb}}
.vide{{color:#6b7280;font-style:italic}}.aide{{color:#4b5563;font-size:14px}}ol li,ul li{{margin:3px 0}}
@media print{{body{{margin:0}}h2{{page-break-after:avoid}}tr{{page-break-inside:avoid}}}}</style></head><body>
<h1>Fiche pour {e(aut)}</h1>
<p class="sous">{e(v['corpus'])} · version du modèle {e(v['version'])} · document produit automatiquement par le noyau</p>
<p class="intro">Cette fiche rassemble ce que l'usage du dispositif fait remonter et qui appelle votre regard : les liens que les apprenants construisent, les notions que vos textes réunissent sans relation explicite dans la base, et ce qui reste à valider. Rien n'y est tranché : chaque point est une proposition que vous pouvez confirmer, corriger ou écarter.</p>

<h2>En bref</h2>
<ul><li>Socle : <b>{v['socle']['nombre']}</b> textes ou passages de référence.</li>
<li>Propositions de l'IA encore à valider : <b>{e(at)}</b>.</li>
<li>Validations enregistrées à ce jour : <b>{m.get('validations', 0)}</b> ; corrections : <b>{len(v['corrections_faites'])}</b>.</li>
<li>Apprenants dont les trajectoires sont prises en compte : <b>{v['divergences']['nombre_apprenants']}</b> (données anonymisées).</li></ul>
<p class="aide">Points de vigilance du dispositif :</p><ul class="aide">{alertes}</ul>

<h2>1. Les liens construits par les apprenants</h2>
<p class="aide">Ce que les apprenants ont relié en répondant aux questions, et la situation de ce lien dans la base. Un lien repris dans plusieurs descriptions est une lecture stable ; un lien absent de la base est une lecture personnelle qui mérite votre avis.</p>
{table(['Lien', 'Fréquence', 'Situation dans la base'], lignes_app)}

<h2>2. Notions que vos textes réunissent souvent, sans relation dans la base</h2>
<p class="aide">Paires de notions présentes ensemble dans plusieurs documents du socle. Faut-il qualifier leur relation, et comment ?</p>
{table(['Notions', 'Réunies dans'], lignes_rel)}
{"<h2>3. Correspondances de traduction attestées dans vos traductions</h2><p class='aide'>Traductions que vous employez de façon répétée et qui pourraient devenir des règles.</p>" + table(['Proposition', 'Attestations', 'Statut actuel du glossaire'], lignes_term) if lignes_term else ""}
<h2>{'4' if lignes_term else '3'}. Corrections déjà faites</h2>
{table(['Élément', 'Statut', 'Version proposée', 'Version corrigée'], lignes_cor)}
{"<h2>Écarts les plus forts entre traduction IA et votre traduction</h2>" + table(['Passage', 'Similarité (0 à 1)'], lignes_div) if lignes_div else ""}
<h2>Éléments faiblement fondés retenus par les apprenants</h2>
<p class="aide">Éléments encore non validés que les apprenants utilisent : les valider ou les corriger en priorité aurait le plus d'effet.</p>
{table(['Élément', 'Nombre de descriptions'], faibles)}

<h2>Comment répondre</h2>
<ol><li>Ouvrez l'application « {'Explorer la MCR' if 'MCR' in v['corpus'] else 'Explorer les textes tibétains'} » fournie avec cette fiche.</li>
<li>Cliquez <b>Validation</b> et entrez le code transmis par le projet.</li>
<li>Corrigez ou validez les éléments concernés, en ajoutant un commentaire si besoin.</li>
<li>Cliquez <b>Exporter la validation</b> et renvoyez le fichier au projet. Il sera intégré au prochain tour de boucle.</li></ol>
<p class="aide">Pour les liens des apprenants (§1) et les notions à relier (§2), un simple courriel ou une annotation sur cette fiche imprimée suffit pour l'instant.</p>
</body></html>"""
