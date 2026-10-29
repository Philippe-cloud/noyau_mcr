# Noyau – modèle de connaissances relativisé et auditable

Le noyau est un prototype de recherche. Il trace la **genèse** de chaque connaissance : qui l'a produite, à partir de quoi, par quelle opération, et qui l'a validée. Il mesure ensuite à quel point chaque élément est **ancré** dans un socle d'autorité, et encadre l'usage d'une IA : une consigne avant qu'elle réponde, un contrôle après sa réponse.

Le corpus fourni est celui de la **Méthode de Conceptualisation Relativisée (MCR)** de Mioara Mugur-Schächter : 51 documents (D11–D61), leurs résumés français et anglais, 33 concepts, des relations et des questions. Les résumés, définitions, relations et questions ont été **proposés par une IA** et sont à valider. Les documents eux-mêmes forment le socle.

> Statut : prototype. Les poids, les seuils et les règles proposées sont provisoires.

## Principes

- **Socle et lectures.** Le point d'entrée est la connaissance telle que décrite par une autorité, avec sa trace. Tout le reste (résumés, concepts, relations, réponses d'IA, trajectoires d'apprenants) est une lecture de ce socle, située par rapport à lui.
- **Genèse.** Chaque élément porte sa chaîne de provenance selon W3C PROV. Les validations sont des témoignages séparés : un agent, un rôle, un statut, une date, un commentaire. L'original d'un texte corrigé est conservé.
- **Indice d'ancrage.** Il combine six composantes : source, transformations, origine, validation, indépendance de la validation, concordance. Il est toujours relatif à la chaîne de genèse ; ce n'est pas une mesure de vérité.
- **Moniteur de boucle.** Il suit la part validée, la **part d'origine IA dans le validé** (le signal de circularité), la diversité des validateurs et le taux de rejet, et émet des alertes.
- **Garde-fous SHACL.** Toute entité a une genèse ; aucun contenu d'IA n'est validé sans un validateur humain.
- **Trajectoires et IA.** L'IA n'est pas réentraînée ; les trajectoires la situent au moment de répondre. Chaque élément fourni porte un signal d'**usage** (combien de descriptions d'apprenants l'ont retenu pour cette question) ; c'est un signal d'utilité, jamais de validité. Avec `--apprenant`, la consigne inclut le **chemin de l'apprenant** : questions posées, éléments déjà retenus, liens construits et leur situation par rapport au socle. La vue IA mesure l'**écart IA/apprenants** : part de ce que les apprenants ont retenu qui figurait dans la sélection fournie à l'IA (rappel), et ce qu'elle omet.
- **Vues.** Une vue pour l'autorité (règles proposées, divergences), une pour l'IA (sa trajectoire de témoin, jamais socle), une trajectoire enrichie pour chaque apprenant, avec la comparaison des trois vues, et une **fiche lisible pour l'autorité** (`fiche_autorite_mcr.html`).

## Utilisation dans le navigateur, sans rien installer

**Boucle automatique (GitHub Actions)**
1. Déposer un fichier de validation dans `corpus/mcr/entrees/validations/`, ou une trajectoire dans `corpus/mcr/entrees/trajectoires/`.
2. La boucle se lance seule. On peut aussi la lancer à la main : Actions → « Boucle du noyau » → Run workflow.
3. Télécharger l'artefact **sorties** : l'application régénérée, les vues et le moniteur.

**Interface complète (Codespaces)**
1. Code → Codespaces → Create codespace.
2. Dans le terminal :
```
pip install -r requirements.txt
python noyau_app.py --sans-navigateur
```
3. Ouvrir le port 8765 dans le navigateur.

**Application Windows**
1. Actions → « Construire l'application Windows (.exe) » → Run workflow.
2. Télécharger l'artefact **NoyauAncrage-Windows**.

L'exécutable n'est pas signé. Au premier lancement : « Informations complémentaires », puis « Exécuter quand même ».

## Utilisation en local (Python 3.10+)

```
python -m pip install -r requirements.txt
python noyau_app.py                      # interface dans le navigateur
python -m ancrage boucle corpus/mcr      # construire + vues + application régénérée
python -m ancrage etat corpus/mcr
python -m ancrage element corpus/mcr C:n01
python -m ancrage interroger corpus/mcr "Qu’est-ce qu’une opération de génération ?" --consigne [--apprenant NOM]
python -m ancrage apprenants corpus/mcr
python -m ancrage controler  corpus/mcr "Qu’est-ce qu’une opération de génération ?" exemples/reponse_fautive.txt
python -m ancrage comparer corpus/mcr
python exemples/test_garde_fou.py
```

## Retours de l'IA

Dans l'application, l'onglet *Ma trajectoire* propose « Demander un retour » : Claude lit la dernière description d'une plante avec les éléments de la base (et leurs statuts) et commente le chemin de l'apprenant. Chaque phrase cite ses appuis ; un contrôle intégré vérifie le retour (identifiants du paquet seulement, éléments « proposés » présentés comme tels) avant de l'afficher.

Le retour est enregistré dans la trajectoire (`retours_ia`) et remonte au noyau avec elle. Le noyau en fait :
- une entité `RET:` (le retour, dérivé des descriptions de l'apprenant et des éléments cités) ;
- une entité `PIA:` par proposition à l'autorité (définition, relation, question), au statut « proposé », plafonnée tant que Mioara ne l'a pas examinée — sauf si le contrôle a refusé le retour.

Les propositions apparaissent dans la fiche de l'autorité et dans l'onglet « Propositions IA » du mode Validation. La vue IA indique en retour comment ses réponses ont passé le contrôle. Un retour produit hors de l'application peut être déposé dans `corpus/mcr/entrees/propositions_ia/` au format `propositions-ia-mcr-v1` (exemple fictif dans `exemples/donnees_simulees/`).

## Organisation

```
ancrage/            noyau : graphe, adaptateurs, calcul, RDF/SHACL, interrogation, vues, régénération
  regles/           formes.ttl (garde-fous SHACL), seuils.json (seuils de gouvernance)
applications/mcr/   interface de l'application « Explorer la MCR » (les données y sont injectées)
corpus/mcr/entrees/ corpus_mcr.json, validations/, trajectoires/, propositions_ia/
interface/          interface de l'application de bureau
noyau_app.py        application de bureau (serveur local + navigateur)
exemples/           réponses d'IA de test, test des garde-fous, données simulées
.github/workflows/  boucle automatique, construction de l'exe Windows
```

## Données simulées

`exemples/donnees_simulees/` contient une validation, une trajectoire et des propositions IA **fictives**, pour les tests uniquement. Ce ne sont pas des validations de Mioara Mugur-Schächter. Pour les essayer, les copier temporairement dans `corpus/mcr/entrees/validations/` et `trajectoires/`, lancer la boucle, puis les retirer.

## Limites

- Aucune IA n'est appelée : le noyau prépare la consigne et contrôle la réponse.
- La recherche des concepts pour une question libre est lexicale.
- Les règles proposées sont induites par comptage.
- Les règles en vigueur ne sont pas encore des éléments du graphe versionnés.
- Les interfaces n'affichent pas encore la genèse ni les indices.
