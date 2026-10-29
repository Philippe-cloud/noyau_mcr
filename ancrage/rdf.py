"""Traduction du graphe interne en RDF (SKOS + PROV-O + Dublin Core),
vérification SHACL et export JSON-LD pondéré."""
import json, os
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS, SKOS, PROV, DCTERMS, XSD

EX = Namespace("https://noyau-ancrage.org/voc#")
ICI = os.path.dirname(__file__)


def _u(base, eid):
    from urllib.parse import quote
    return URIRef(base + quote(eid, safe=""))


def vers_rdf(g, base="https://noyau-ancrage.org/corpus/"):
    G = Graph()
    for p, n in (("skos", SKOS), ("prov", PROV), ("dcterms", DCTERMS), ("ex", EX)):
        G.bind(p, n)
    A = {}
    for aid, a in g.d["agents"].items():
        u = _u(base + "agent/", aid); A[aid] = u
        G.add((u, RDF.type, PROV.Agent))
        G.add((u, RDF.type, {"humain": PROV.Person, "ia": PROV.SoftwareAgent, "collectif": PROV.Organization}[a["type"]]))
        G.add((u, RDFS.label, Literal(a["nom"], lang="fr")))
        if a["role"]:
            G.add((u, EX.role, Literal(a["role"], lang="fr")))
    U = {eid: _u(base, eid) for eid in g.E}
    TYP = {"source": DCTERMS.BibliographicResource, "passage": EX.Passage, "traduction": EX.Traduction,
           "concept": SKOS.Concept, "definition": EX.Definition, "relation": EX.Relation,
           "question": EX.Question, "description": EX.Description, "resume": EX.Resume,
           "retour": EX.RetourIA, "proposition": EX.PropositionIA}
    for eid, e in g.E.items():
        u = U[eid]; c = e["contenu"]
        G.add((u, RDF.type, PROV.Entity)); G.add((u, RDF.type, TYP[e["type"]]))
        G.add((u, DCTERMS.identifier, Literal(eid)))
        if e["type"] == "concept":
            G.add((u, SKOS.prefLabel, Literal(c["libelle"], lang="fr")))
            if c.get("tib"): G.add((u, SKOS.altLabel, Literal(c["tib"], lang="bo")))
            if c.get("wylie"): G.add((u, SKOS.altLabel, Literal(c["wylie"], lang="bo-Latn")))
            G.add((u, EX.statutGlossaire, Literal(c["statut_glossaire"])))
        elif e["type"] == "definition":
            G.add((u, SKOS.definition, Literal(c["texte"], lang="fr")))
        elif e["type"] == "relation":
            G.add((u, EX.de, U[c["de"]])); G.add((u, EX.vers, U[c["vers"]])); G.add((u, RDFS.label, Literal(c["libelle"], lang="fr")))
            G.add((U[c["de"]], SKOS.related, U[c["vers"]]))
        elif e["type"] == "source":
            G.add((u, DCTERMS.title, Literal(c["titre"], lang="fr")))
            G.add((u, DCTERMS.creator, A[e["prov"]["operateur"]]))
            if c.get("date"): G.add((u, DCTERMS.date, Literal(c["date"])))
            if c.get("lien"): G.add((u, RDFS.seeAlso, URIRef(c["lien"])))
        elif e["type"] in ("passage", "traduction"):
            G.add((u, EX.texte, Literal(c["texte"], lang=c["langue"])))
        elif e["type"] == "resume":
            G.add((u, EX.texte, Literal(c["texte"], lang="fr")))
            if c.get("texte_en"): G.add((u, EX.texte, Literal(c["texte_en"], lang="en")))
            G.add((u, EX.base, Literal(c["base"], lang="fr")))
        elif e["type"] == "question":
            G.add((u, RDFS.label, Literal(c["texte"], lang="fr")))
            for k in c["concepts"]: G.add((u, EX.porteSur, U[k]))
        elif e["type"] == "description":
            G.add((u, RDFS.label, Literal(c["question"], lang="fr")))
            for k in c["elements"]: G.add((u, EX.retient, U[k]))
        elif e["type"] == "retour":
            G.add((u, EX.texte, Literal(c["texte"], lang="fr")))
            if c["controle"].get("verdict"): G.add((u, EX.verdictControle, Literal(c["controle"]["verdict"])))
        elif e["type"] == "proposition":
            G.add((u, EX.nature, Literal(c["nature"]))); G.add((u, EX.texte, Literal(c["texte"], lang="fr")))
            if c.get("cible") in U: G.add((u, EX.porteSur, U[c["cible"]]))
        # provenance : activité de génération
        act = _u(base + "activite/", "gen:" + eid)
        G.add((u, PROV.wasGeneratedBy, act)); G.add((act, RDF.type, PROV.Activity))
        G.add((act, EX.operation, Literal(e["prov"]["operation"])))
        if e["prov"]["operateur"]:
            G.add((act, PROV.wasAssociatedWith, A[e["prov"]["operateur"]]))
            G.add((u, PROV.wasAttributedTo, A[e["prov"]["operateur"]]))
        if e["prov"]["date"]:
            G.add((act, PROV.endedAtTime, Literal(e["prov"]["date"])))
        for p in e["prov"]["derive_de"]:
            G.add((u, PROV.wasDerivedFrom, U[p]))
        G.add((u, EX.statut, Literal(g.statut(eid))))
        if "ancrage" in e:
            an = e["ancrage"]
            G.add((u, EX.ancrage, Literal(an["indice"], datatype=XSD.decimal)))
            G.add((u, EX.niveau, Literal(an["niveau"])))
            G.add((u, EX.composantes, Literal(json.dumps(an["composantes"]))))
    for p, c in g.d["mentions"]:
        G.add((U[p], EX.mentionne, U[c]))
    for i, v in enumerate(g.d["validations"]):
        act = _u(base + "activite/", f"val:{i}")
        G.add((act, RDF.type, PROV.Activity)); G.add((act, RDF.type, EX.Validation))
        G.add((act, PROV.used, U[v["entite"]]))
        if v["agent"] in A: G.add((act, PROV.wasAssociatedWith, A[v["agent"]]))
        G.add((act, EX.statut, Literal(v["statut"])))
        if v["role"]: G.add((act, EX.role, Literal(v["role"], lang="fr")))
        if v["date"]: G.add((act, PROV.endedAtTime, Literal(v["date"])))
        if v["commentaire"]: G.add((act, RDFS.comment, Literal(v["commentaire"], lang="fr")))
    return G


def verifier(G):
    from pyshacl import validate
    formes = Graph().parse(os.path.join(ICI, "regles", "formes.ttl"), format="turtle")
    ok, rg, txt = validate(G, shacl_graph=formes, inference="none", abort_on_first=False)
    res = []
    SH = Namespace("http://www.w3.org/ns/shacl#")
    for r in rg.subjects(RDF.type, SH.ValidationResult):
        res.append({"noeud": str(rg.value(r, SH.focusNode)), "message": str(rg.value(r, SH.resultMessage)),
                    "gravite": str(rg.value(r, SH.resultSeverity)).split("#")[-1]})
    return ok, res


CONTEXTE = {"skos": str(SKOS), "prov": str(PROV), "dcterms": str(DCTERMS), "ex": str(EX),
            "rdfs": str(RDFS), "xsd": str(XSD)}


def exporter_jsonld(G, chemin):
    txt = G.serialize(format="json-ld", context=CONTEXTE, indent=1)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(txt)
    return chemin
