"""Ligne de commande du noyau d'ancrage.

  python -m ancrage construire  <corpus>            ingérer, vérifier, calculer, exporter une version datée
  python -m ancrage etat        <corpus>            moniteur de boucle de la dernière version
  python -m ancrage element     <corpus> <id>       chaîne de provenance et indice d'un élément
  python -m ancrage interroger  <corpus> "<question>" [--consigne]
  python -m ancrage controler   <corpus> "<question>" <reponse.txt>
  python -m ancrage comparer    <corpus> [<v1> <v2>] comparer deux versions (par défaut les deux dernières)
  python -m ancrage exporter-vues <corpus>          vues autorité, IA, trajectoires enrichies, moniteur
  python -m ancrage mettre-a-jour-app <corpus>      régénérer l'application HTML à partir de la dernière version
  python -m ancrage boucle      <corpus>            construire + exporter-vues + mettre-a-jour-app
"""
import sys, os, json, glob, importlib, datetime
from .graphe import Graphe
from . import calcul, rdf, interroger as Q, vues


def _derniere(corpus, n=1):
    vs = sorted(glob.glob(os.path.join(corpus, "versions", "*.graphe.json")))
    if len(vs) < n:
        sys.exit("Aucune version : lancez d'abord « construire ».")
    return vs[-n:]


def construire(corpus):
    nom = os.path.basename(os.path.normpath(corpus))
    ad = importlib.import_module(f".adaptateurs.{nom}", "ancrage")
    g = ad.ingerer(corpus)
    calcul.tout_calculer(g)
    G = rdf.vers_rdf(g)
    ok, res = rdf.verifier(G)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    g.d["version"] = stamp
    g.d["moniteur"] = calcul.moniteur(g)
    g.d["shacl"] = {"conforme": ok, "violations": res}
    os.makedirs(os.path.join(corpus, "versions"), exist_ok=True)
    base = os.path.join(corpus, "versions", f"{nom}_{stamp}")
    g.sauver(base + ".graphe.json")
    rdf.exporter_jsonld(G, base + ".jsonld")
    m = g.d["moniteur"]
    print(f"Version {stamp} : {m['entites']} entités, {m['validations']} validations, {len(G)} triplets RDF")
    print(f"SHACL : {'conforme' if ok else str(len(res)) + ' violation(s)'}")
    for r in res[:10]:
        print(f"  - [{r['gravite']}] {r['noeud'].rsplit('/', 1)[-1]} : {r['message']}")
    etat_affiche(m)
    print(f"→ {base}.jsonld\n→ {base}.graphe.json")


def etat_affiche(m):
    print("Moniteur de boucle :")
    for k in ("part_validee", "part_origine_ia_dans_valide", "ecart_ia_reference", "score_temoin", "taux_rejet", "ancrage_moyen"):
        print(f"  {k:30s} {m[k]}")
    print(f"  validateurs humains            {', '.join(m['validateurs_humains'])}")
    for a in m["alertes"]:
        print("  ALERTE :", a)


def main(a):
    if len(a) < 2:
        print(__doc__); return
    cmd, corpus = a[0], a[1]
    if cmd == "construire":
        return construire(corpus)
    if cmd == "boucle":
        construire(corpus)
        main(["exporter-vues", corpus]); main(["mettre-a-jour-app", corpus]); return
    g = Graphe.charger(_derniere(corpus)[0])
    if cmd == "etat":
        print("Version", g.d["version"]); etat_affiche(g.d["moniteur"])
    elif cmd == "element":
        eid = a[2]; e = g.E[eid]
        print(json.dumps({"id": eid, "type": e["type"], "statut": g.statut(eid), "ancrage": e["ancrage"],
                          "chaine": g.chaine(eid), "validations": g.validations_de(eid)}, ensure_ascii=False, indent=1))
    elif cmd == "interroger":
        p = Q.interroger(g, a[2])
        print(Q.consigne(p) if "--consigne" in a else json.dumps(p, ensure_ascii=False, indent=1))
    elif cmd == "controler":
        p = Q.interroger(g, a[2])
        print(json.dumps(Q.controler(p, open(a[3], encoding="utf-8").read()), ensure_ascii=False, indent=1))
    elif cmd == "comparer":
        v1, v2 = (a[2], a[3]) if len(a) > 3 else _derniere(corpus, 2)
        A, B = Graphe.charger(v1), Graphe.charger(v2)
        print(f"{A.d['version']} → {B.d['version']}")
        ch = []
        for k, e in B.E.items():
            if k in A.E:
                d = e["ancrage"]["indice"] - A.E[k]["ancrage"]["indice"]
                s1, s2 = A.statut(k), B.statut(k)
                if abs(d) > 0.001 or s1 != s2:
                    ch.append((d, k, s1, s2, A.E[k]["ancrage"]["indice"], e["ancrage"]["indice"]))
            else:
                ch.append((e["ancrage"]["indice"], k, "—", B.statut(k), 0, e["ancrage"]["indice"]))
        for d, k, s1, s2, x, y in sorted(ch, key=lambda t: -abs(t[0])):
            print(f"  {k:28s} {s1:9s}→ {s2:9s} ancrage {x:.3f} → {y:.3f} ({d:+.3f})")
        for k in ("part_validee", "part_origine_ia_dans_valide", "ancrage_moyen"):
            print(f"  moniteur {k}: {A.d['moniteur'][k]} → {B.d['moniteur'][k]}")
    elif cmd == "exporter-vues":
        out, fs = vues.exporter(g, corpus)
        print(f"Vues de la version {g.d['version']} → {out}")
        for f in fs: print("  -", f)
    elif cmd == "mettre-a-jour-app":
        from . import application
        print("Application régénérée →", application.regenerer(g, corpus))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
