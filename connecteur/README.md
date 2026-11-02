# Connecteur « témoin » du noyau MCR

Un serveur MCP (*Model Context Protocol*) qui permet à une IA, Claude ou une autre, d'explorer le corpus de la MCR avec des outils :
`chercher`, `lire_document`, `lire_notion`, `voir_relations`, `lister_questions`, puis `declarer_chemin`.

**Chaque appel est enregistré par le serveur, pas par l'IA** : c'est le chemin réel. Quand l'IA déclare son chemin, la page `/journal` compare :
- les **embellissements** : ce qu'elle dit avoir lu sans l'avoir ouvert ;
- les **citations sans lecture** : ce qu'elle cite dans sa réponse sans l'avoir ouvert ;
- les **omissions** : ce qu'elle a ouvert sans le déclarer ;
- un **accord** entre déclaré et réel (de 0 à 1).

Le serveur ne voit que ce qui passe par lui : s'il manque une source dans le chemin réel, c'est que l'IA l'a prise ailleurs (sa mémoire, le web).

## Mise en ligne (depuis le navigateur, gratuit)

Les intitulés de Cloudflare peuvent varier légèrement.

1. **Créer un compte** sur https://dash.cloudflare.com (offre gratuite).
2. **Créer le stockage du journal** : *Storage & Databases → KV → Create namespace*, nommez-le `noyau-journal`, puis copiez son **identifiant**.
3. **Sur GitHub**, ouvrez `connecteur/wrangler.toml`, cliquez sur le crayon, retirez les `#` des trois dernières lignes, collez l'identifiant à la place de `COLLER_ICI`, puis *Commit changes*.
4. **Dans Cloudflare** : *Workers & Pages → Create → Import a repository*, reliez votre compte GitHub, choisissez `noyau_mcr`, indiquez **`connecteur`** comme dossier racine (*root directory*), puis *Deploy*. Chaque modification du dossier sur GitHub redéploiera le connecteur.
5. **Protéger le journal** : dans le Worker, *Settings → Variables and secrets → Add*, type *Secret*, nom `JOURNAL_KEY`, valeur de votre choix (un mot de passe).
6. **Vérifier** : ouvrez `https://noyau-mcr.<votre-sous-domaine>.workers.dev/`. La page d'accueil donne l'adresse du connecteur et signale si le stockage n'est pas relié.
7. **Relier Claude** : dans Claude, *Paramètres → Connecteurs → Ajouter un connecteur personnalisé*, adresse `https://noyau-mcr.<votre-sous-domaine>.workers.dev/mcp`. (La possibilité d'ajouter un connecteur personnalisé dépend de l'abonnement.)

## Utilisation

Posez à Claude une question sur la MCR en lui demandant d'utiliser le connecteur et de terminer par `declarer_chemin`. Puis ouvrez :

`https://noyau-mcr.<votre-sous-domaine>.workers.dev/journal?cle=<votre JOURNAL_KEY>`

## À savoir

- Le journal (outils appelés, arguments, déclaration de l'IA) est stocké chez Cloudflare, dans votre compte. Il est protégé par la clé, mais n'y mettez rien de confidentiel.
- Offre gratuite de KV : environ 1 000 écritures par jour, largement suffisant pour des essais.
- Version 0.1 : les appels d'une même session sont écrits les uns après les autres ; des appels simultanés pourraient se chevaucher.
- Les résumés et définitions servis sont ceux du corpus, au statut « proposé, non validé » tant que Mioara ne les a pas validés. Pour mettre à jour les données : régénérer `corpus.json` à partir de `corpus/mcr/entrees/corpus_mcr.json`.
- Test local : `node connecteur/test_local.mjs` (Node 22 ou plus) simule une IA qui embellit son chemin.
