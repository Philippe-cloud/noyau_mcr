"""Test des garde-fous : une IA qui « valide » son propre contenu doit être refusée par SHACL."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ancrage.adaptateurs import mcr
from ancrage import calcul, rdf

g = mcr.ingerer("corpus/mcr")
g.valider("DEF:n07", "ia", "valide", role="auto-validation (interdite)")   # l'IA se valide elle-même
g.E["RES:D12"]["prov"]["operateur"] = None                               # genèse amputée
calcul.tout_calculer(g)
ok, res = rdf.verifier(rdf.vers_rdf(g))
print("Conforme :", ok)
for r in res:
    print(f" - {r['noeud'].rsplit('/', 1)[-1]} : {r['message']}")
