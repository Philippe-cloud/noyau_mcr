# Noyau – modèle de connaissances relativisé et auditable

Le noyau est un prototype de recherche. Il trace la **genèse** de chaque connaissance : qui l'a produite, à partir de quoi, par quelle opération, et qui l'a validée. Il mesure à quel point chaque élément est **ancré** dans un socle d'autorité. Il soumet à la même exigence de traçabilité les trois acteurs d'un savoir : l'**autorité** qui le valide, l'**apprenant** qui se l'approprie, et l'**IA** qui le reprend.

Le corpus fourni est celui de la **Méthode de Conceptualisation Relativisée (MCR)** de Mioara Mugur-Schächter : 51 documents (D11–D61), leurs résumés français et anglais, 33 concepts, des relations et des questions. Les résumés, définitions, relations et questions ont été **proposés par une IA** et sont à valider. Les documents eux-mêmes forment le socle.

> Statut : prototype de recherche. Les poids, les seuils et les règles sont provisoires et doivent être fixés avec les autorités.

## Sommaire

- [Principes](#principes)
- [Les outils en ligne](#les-outils-en-ligne)
- [La boucle du noyau](#la-boucle-du-noyau)
- [Protocole de trace commun](#protocole-de-trace-commun-trace-v1)
- [Étiquettes de provenance](#étiquettes-de-provenance)
- [Retours et propositions de l'IA](#retours-et-propositions-de-lia)
- [Audit d'une réponse d'IA](#audit-dune-réponse-dia)
- [Connecteur « témoin »](#connecteur--témoin--mcp)
- [Utilisation en local](#utilisation-en-local)
- [Organisation du dépôt](#organisation-du-dépôt)
- [Limites](#limites)

## Principes

- **Socle et lectures.** Le point d'entrée est la connaissance telle que décrite par une autorité, avec sa trace. Tout le reste (résumés, concepts, relations, réponses d'IA, trajectoires d'apprenants) est une lecture de ce socle, située par rapport à lui.
- **Genèse.** Chaque élément porte sa chaîne de provenance selon W3C PROV. Les validations sont des témoignages séparés : un agent, un rôle, un statut, une date, un commentaire. L'original d'un texte corrigé est conservé.
- **Indice d'ancrage.** Il combine six composantes : source, transformations, origine, validation, indépendance de la validation, concordance. Il est relatif à la chaîne de genèse et ne mesure pas la vérité. Un contenu d'IA non validé est plafonné à 0,5.
- **Moniteur de circularité.** Il suit la part validée, la **part d'origine IA dans ce qui est validé**, la diversité des validateurs et le taux de rejet, et émet des alertes. Sans ce garde-fou, une IA qui apprend de ses propres productions s'enferme dans ses erreurs.
- **Garde-fous SHACL.** Toute entité a une genèse, et aucun contenu d'IA n'est validé sans un validateur humain.
- **Usage n'est pas validité.** Qu'un élément soit beaucoup retenu par les apprenants est un signal d'utilité, jamais une preuve de validité.
- **Trois niveaux de trace.** Une trace est **déclarative** quand l'acteur raconte son chemin, **témoignée** quand un environnement indépendant enregistre ses actions, et **vérifiée** quand un tiers en contrôle un échantillon. Le noyau vise le passage de la première à la troisième.
- **Communicable plutôt que consensuel.** Le but n'est pas que tous soient d'accord, mais que chacun puisse voir d'où vient un savoir, comment il a été affirmé, et en juger.

## Les outils en ligne

| Outil | Adresse | Rôle |
|---|---|---|
| **Explorer la MCR** | https://philippe-cloud.github.io/noyau_mcr/ | parcourir le corpus en plantes, tracer sa trajectoire, valider (mode autorité) |
| **Étiqueteuse** | https://philippe-cloud.github.io/noyau_mcr/etiqueteuse/ | créer des étiquettes de provenance pour des éléments archivés |
| **Trajectoire** | https://philippe-cloud.github.io/noyau_mcr/trajectoire/ | déposer des documents, faire proposer leur étiquette par l'IA, la valider, voir l'arbre des vues et interroger ce noyau (l'IA ne fonctionne que dans la version Claude ; ici, l'étiquette se remplit à la main) |
| **Exemple de filiation** | https://philippe-cloud.github.io/noyau_mcr/exemples/filiation_tendances_IA.html | graphe dynamique du chemin réel d'une recherche d'IA, action par action |

Ces pages sont publiques et republiées à chaque passage de la boucle. Elles fonctionnent sans compte. Les fonctions qui font appel à l'IA (« Demander un retour », « Demander le chemin de l'IA ») ne fonctionnent que dans la version publiée sur claude.ai.

Dans **Explorer la MCR** :
- *Ma plante* : une question fait pousser une plante, avec des notions (racines) et des documents (branches) ; on retient, on écarte (avec une raison facultative), on relie, puis on enregistre une description datée, avec « ce que je sais expliquer ».
- *Ma trajectoire* : toutes les descriptions dans le temps, la stabilité W, et le **retour de l'IA**.
- *Mon chemin* : son chemin dans l'ordre réel, puis **trois chemins côte à côte** pour la même question (le socle, le sien, celui de l'IA) et leur lecture croisée ; export dans le protocole commun.
- *Validation* (code réservé à l'autorité) : résumés, définitions, relations, questions et propositions de l'IA.

## La boucle du noyau

1. Déposer dans `corpus/mcr/entrees/` un fichier de validation (`validations/`), une trajectoire (`trajectoires/`) ou des propositions d'IA (`propositions_ia/`).
2. La boucle se lance seule sur GitHub (Actions → « Boucle du noyau »), ou à la main avec *Run workflow*.
3. Elle produit l'artefact **sorties** : l'application régénérée, la **fiche lisible pour l'autorité**, les vues (autorité, IA, trajectoires enrichies), le moniteur, et les traces de l'autorité et des apprenants dans le protocole commun. Elle republie aussi les pages en ligne.

Autres manières de l'utiliser : **Codespaces** (Code → Codespaces, puis `python noyau_app.py --sans-navigateur` et ouvrir le port 8765), ou l'**application Windows** (Actions → « Construire l'application Windows (.exe) », artefact *NoyauAncrage-Windows* ; l'exécutable n'est pas signé).

## Protocole de trace commun (trace-v1)

Une même grammaire pour l'autorité, l'apprenant et l'IA (`ancrage/trace.py`). Pour chaque chemin vers une question :
- les **recherches** : ce qui a été consulté, retenu ou écarté, avec la raison, dans l'ordre réel ;
- les **étapes**, avec leurs appuis, de nature « sourcée » ou « savoir propre » ;
- les **relations**, avec leur origine : *base*, *indexation* (rejoint l'indexation d'un document par la base) ou *propre* (lecture personnelle) ;
- les **affirmations**, avec leurs appuis.

Côté autorité, la **trajectoire fondatrice** est reconstituée à partir de la suite datée des validations (`trace_autorite.json`). Côté apprenant, elle vient de sa trajectoire (`trace_apprenant_*.json`). Côté IA, elle vient de *Mon chemin* ou d'un audit.

Le savoir propre n'a pas le même statut selon l'acteur : contribution fondatrice pour l'autorité, vue légitime pour l'apprenant, part non vérifiable pour l'IA. Le plafond d'ancrage ne vaut que pour l'IA.

## Étiquettes de provenance

Comme l'étiquette cousue dans un vêtement, une étiquette de provenance accompagne chaque élément archivé et dit, toujours dans le même ordre : **composition** (sources, pages, ce qu'on en a fait), **fabrication**, **validations**, **statut et vue**, **filiation**, **usage** (citation, diffusion, entraînement des IA). Ce qui manque reste marqué « non renseigné ».

L'**Étiqueteuse** (`applications/etiqueteuse/`) les crée, contrôle leur conformité au profil MCR v0.1, conserve les versions successives, et les exporte en JSON-LD (vocabulaire W3C PROV) à joindre au document ou à insérer dans sa page web.

Une étiquette peut aussi se **calculer à partir des actions** sur le document (consulté, utilisé, rejeté, mène vers) : c'est ce que montre l'exemple de filiation (`exemples/filiation/`), où chaque source porte l'étiquette de ce que l'IA en a réellement fait.

Le modèle Word `modeles/Fiche_audit_validation.docx` sert à l'autorité ou à un auditeur pour documenter chaque validation à la main : textes vérifiés, pages, constat, décision, pourquoi, et report dans la base.

## Retours et propositions de l'IA

Dans *Ma trajectoire*, « Demander un retour » fait lire à Claude la dernière description d'une plante avec les éléments de la base et leurs statuts. Chaque phrase du retour cite ses appuis, et un contrôle intégré le vérifie avant affichage. Les relations déjà présentes dans la base sont écartées des propositions.

Le retour est enregistré dans la trajectoire et remonte au noyau, qui en fait une entité `RET:` et une entité `PIA:` par proposition à l'autorité, au statut « proposé » et plafonnée. Les propositions apparaissent dans la fiche de l'autorité et dans l'onglet « Propositions IA » du mode Validation. Celles d'un retour refusé par le contrôle ne sont pas transmises.

## Audit d'une réponse d'IA

Une IA répond en déclarant sa trajectoire (`trajectoire-ia-v1`) : recherches dans l'ordre réel, sources retenues et rejetées avec leur raison, étapes de raisonnement, relations, et affirmations avec leurs appuis et « ce que dit la source ». Le moteur de règles l'audite **sur une copie du graphe** : l'audit ne modifie jamais la base.

- `python -m ancrage consigne-audit corpus/mcr "question"` donne la consigne à fournir à l'IA.
- Déposer la réponse dans `corpus/mcr/audits_ia/entrees/` lance le traitement « Audit d'une réponse d'IA », qui produit `audit.html` et `audit.json`.
- `python -m ancrage auditer-ia --sans-corpus fichier.json` audite une réponse à une question hors corpus : les sources consultées tiennent lieu de socle provisoire, et ce qui vient du seul entraînement du modèle doit être déclaré comme « savoir interne ».

Exemple réel : `exemples/trajectoire_ia_evolutions_IA.json`. Limite assumée : une trace déclarée par l'IA mesure son honnêteté, pas son chemin réel. C'est la raison d'être du connecteur « témoin ».

## Connecteur « témoin » (MCP)

Le dossier `connecteur/` contient un serveur MCP (*Model Context Protocol*) à héberger sur Cloudflare Workers. Une IA y explore le corpus avec des outils (chercher, lire un document, lire une notion, voir les relations), puis déclare son chemin. **Chaque appel est enregistré par le serveur, pas par l'IA.** La page `/journal` compare le déclaré au réel : embellissements, citations sans lecture, omissions, et un accord de 0 à 1.

Le connecteur ne voit que ce qui passe par lui : ce que l'IA tire de sa mémoire ou du web apparaît comme un écart entre sa réponse et son chemin réel. Procédure de mise en ligne pas à pas : `connecteur/README.md`. Test local : `node connecteur/test_local.mjs`.

## Utilisation en local

Python 3.10 ou plus :
```
python -m pip install -r requirements.txt
python noyau_app.py                      # interface dans le navigateur
python -m ancrage boucle corpus/mcr      # construire + vues + application régénérée
python -m ancrage etat corpus/mcr
python -m ancrage element corpus/mcr C:n01
python -m ancrage interroger corpus/mcr "Qu’est-ce qu’une opération de génération ?" --consigne [--apprenant NOM]
python -m ancrage controler  corpus/mcr "Qu’est-ce qu’une opération de génération ?" exemples/reponse_fautive.txt
python -m ancrage consigne-audit corpus/mcr "Qu’est-ce qu’une vue ?"
python -m ancrage auditer-ia corpus/mcr [fichier.json]
python -m ancrage comparer corpus/mcr
python exemples/test_garde_fou.py
```

## Organisation du dépôt

```
ancrage/               noyau : graphe, adaptateurs, calcul, RDF/SHACL, interrogation, vues,
                       protocole de trace (trace.py), audit d'IA (audit_ia.py), régénération
  regles/              formes.ttl (garde-fous SHACL), seuils.json (seuils de gouvernance)
applications/mcr/      application « Explorer la MCR » (les données y sont injectées)
applications/etiqueteuse/  application « Étiqueteuse »
applications/trajectoire/  application « Trajectoire » (étiquette minimale, trajectoire, arbre des vues, questions au noyau)
corpus/mcr/entrees/    corpus_mcr.json, validations/, trajectoires/, propositions_ia/
corpus/mcr/audits_ia/  réponses d'IA à auditer (séparées de la boucle)
connecteur/            connecteur « témoin » MCP (Cloudflare Workers)
exemples/              réponses d'IA de test, garde-fous, données simulées, exemple de filiation
modeles/               fiche d'audit de validation (Word)
interface/, noyau_app.py   application de bureau
.github/workflows/     boucle et publication des pages, audit d'IA, exe Windows
```

`exemples/donnees_simulees/` contient des validations, trajectoires et propositions **fictives**, pour les tests uniquement. Ce ne sont pas des validations de Mioara Mugur-Schächter.

## Limites

- Les traces de l'IA restent majoritairement **déclaratives** tant que le connecteur « témoin » n'est pas en service ; il ne témoigne que de ce qui passe par lui.
- Le fonctionnement interne des modèles reste hors d'atteinte : le noyau situe la boîte noire, il ne l'ouvre pas.
- Toute la qualité repose sur la **validation humaine**, dont la capacité est limitée : il faut choisir quoi valider en priorité.
- Les règles et les seuils ne sont pas encore des éléments du graphe tracés et versionnés comme le reste.
- La recherche des concepts pour une question libre est lexicale, et les règles proposées sont induites par comptage.
- Les données des pages en ligne restent dans le navigateur de chaque visiteur : elles ne remontent au projet que si on les exporte.
