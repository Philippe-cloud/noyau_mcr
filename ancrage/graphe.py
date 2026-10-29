"""Graphe de connaissances avec provenance (modèle interne).

Le graphe est un dictionnaire sérialisable en JSON. Chaque entité porte sa
chaîne de provenance (dérivée de quoi, par quelle opération, par quel
opérateur, quand). Les validations sont des activités séparées, au sens de
W3C PROV : un agent, un rôle, un statut, une date.
"""
import json, datetime

STATUTS = ("propose", "valide", "variable", "corriger", "rejete", "source")


def maintenant():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


class Graphe:
    def __init__(self, nom):
        self.d = {"format": "noyau-ancrage-v1", "nom": nom, "creeLe": maintenant(),
                  "agents": {}, "entites": {}, "validations": [], "mentions": [], "temoin": []}

    # ---------- construction ----------
    def agent(self, id, nom, type, role=""):
        """type : humain | ia | collectif"""
        self.d["agents"][id] = {"nom": nom, "type": type, "role": role}

    def entite(self, id, type, contenu, derive_de=(), operation="copie", operateur=None, date=None, **meta):
        if operateur and operateur not in self.d["agents"]:
            raise ValueError(f"agent inconnu : {operateur}")
        for x in derive_de:
            if x not in self.d["entites"]:
                raise ValueError(f"{id} dérive d'une entité inconnue : {x}")
        self.d["entites"][id] = {"type": type, "contenu": contenu,
                                 "prov": {"derive_de": list(derive_de), "operation": operation,
                                          "operateur": operateur, "date": maintenant() if date is None else date}, **meta}
        return id

    def valider(self, entite, agent, statut, role="", date=None, commentaire=""):
        if statut not in STATUTS:
            raise ValueError(f"statut inconnu : {statut}")
        if entite not in self.d["entites"]:
            raise ValueError(f"entité inconnue : {entite}")
        self.d["validations"].append({"entite": entite, "agent": agent, "role": role, "statut": statut,
                                      "date": maintenant() if date is None else date, "commentaire": commentaire})

    def mention(self, passage, concept):
        self.d["mentions"].append([passage, concept])

    # ---------- lecture ----------
    @property
    def E(self):
        return self.d["entites"]

    def agent_de(self, eid):
        return self.d["agents"].get(self.E[eid]["prov"]["operateur"] or "", {})

    def validations_de(self, eid):
        """Dernière validation de chaque agent (la plus récente l'emporte)."""
        par = {}
        for v in self.d["validations"]:
            if v["entite"] == eid and (v["agent"] not in par or v["date"] >= par[v["agent"]]["date"]):
                par[v["agent"]] = v
        return list(par.values())

    def statut(self, eid):
        vs = self.validations_de(eid)
        if not vs:
            return "source" if self.E[eid]["type"] == "source" else "propose"
        ordre = {"rejete": 0, "corriger": 1, "propose": 2, "variable": 3, "valide": 4}
        # un rejet par un validateur humain l'emporte ; sinon le meilleur statut
        if any(v["statut"] == "rejete" for v in vs):
            return "rejete"
        return max(vs, key=lambda v: ordre[v["statut"]])["statut"]

    def chaine(self, eid, _vu=None):
        """Chaîne de provenance : liste d'étapes depuis l'entité jusqu'aux sources."""
        _vu = _vu or set()
        if eid in _vu:
            return []
        _vu.add(eid)
        e = self.E[eid]
        etape = {"entite": eid, "type": e["type"], "operation": e["prov"]["operation"],
                 "operateur": e["prov"]["operateur"], "date": e["prov"]["date"]}
        out = [etape]
        for p in e["prov"]["derive_de"][:1]:  # chaîne principale (premier parent)
            out += self.chaine(p, _vu)
        return out

    def lectures(self, x):
        """Lectures dérivées d'une entité du socle (traductions, résumés) : humains d'abord, IA ensuite."""
        if not hasattr(self, "_lect") or self._lect_n != len(self.E):
            self._lect, self._lect_n = {}, len(self.E)
            for k, e in self.E.items():
                if e["type"] in ("traduction", "resume") and e["prov"]["derive_de"]:
                    self._lect.setdefault(e["prov"]["derive_de"][0], []).append(k)
        L = self._lect.get(x, [])
        return sorted(L, key=lambda k: (self.agent_de(k).get("type") == "ia", k))

    def reference(self, x):
        """Lecture humaine validée (référence), ou None."""
        for k in self.lectures(x):
            if self.agent_de(k).get("type") != "ia" and self.statut(k) == "valide":
                return k
        return None

    def proposition_ia(self, x):
        for k in self.lectures(x):
            if self.agent_de(k).get("type") == "ia":
                return k
        return None

    def appui_atteste(self, x):
        """Une mention compte comme attestée si l'entité du socle est validée ou est un texte source."""
        return self.E[x]["type"] == "source" or self.statut(x) == "valide"

    @property
    def config(self):
        return self.d.get("config", {})

    def par_type(self, t):
        return [k for k, e in self.E.items() if e["type"] == t]

    # ---------- persistance ----------
    def sauver(self, chemin):
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)

    @classmethod
    def charger(cls, chemin):
        g = cls("")
        with open(chemin, encoding="utf-8") as f:
            g.d = json.load(f)
        return g
