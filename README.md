# drawer-model

Un système qui **comprend une demande et la dessine** — open-vocabulary, 100 % local
sur Apple Silicon. Le modèle ne produit pas une image raster : il génère un
**programme de traits** (lignes, courbes de Bézier, arcs) qu'un exécuteur trace à la
souris, comme un humain dessinerait dans Paint.

Recette inspirée de **SketchAgent** (un LLM écrit un programme de traits) + un
**critique CLIP** qui juge « ça ressemble à X ? » et ferme une boucle d'amélioration.

## L'idée : marcher avant de courir

On ne demande jamais à un modèle de viser au pixel. On empile des compétences, des
plus simples (et déterministes) aux plus créatives :

```
LA MAIN      gestes certifiés au pixel (ligne, cercle, bézier)      code, vérifié
LE CERVEAU   demande → programme de traits                          LLM (SketchAgent)
LE CRITIQUE  « ressemble à X ? »                                    CLIP local (MPS)
L'APPRENTISSAGE  raffine un programme guidé par CLIP                optim. boîte-noire
LE CORPUS    (demande → programme → score)                          matière du modèle
LE MODÈLE    comprend la demande (FR/EN) et dessine                 récupération sémantique
```

## Composants

| Fichier | Rôle |
|---|---|
| `draw_canvas.html` | la toile (relecture des pixels en JS pour la vérification) |
| `draw_lab.py` | la main : exécuteur de traits via événements souris CDP + **certification au pixel** |
| `draw_figure.py` | le DSL de traits + programmes (cheval, maison…) |
| `draw_seeds.py` | graines de programmes pour ~10 sujets |
| `draw_critic.py` | critique CLIP (juge + encode les demandes) |
| `draw_learn.py` | la machine d'apprentissage (raffine via CLIP) |
| `draw_corpus.py` | la fabrique : construit le corpus de sujets |
| `draw_model.py` | **le modèle** : comprend la demande et dessine |
| `draw_live.py` / `draw_demo.py` | démos visibles (regarde-le dessiner) |
| `draw_mcp.py` | serveur MCP (dessiner / juger / apprendre comme outils) |

## Démarrage

```bash
pip install -r requirements.txt          # websockets, numpy, pillow, torch, transformers, mcp
# nécessite Google Chrome installé (piloté via CDP, souris virtuelle — ne touche pas le vrai curseur)

python draw_lab.py                        # certifie la main (12 gestes, au pixel près)
python draw_demo.py                       # démo live : dessine + CLIP juge son dessin
python draw_model.py --live "un cheval" "un chat" "une voiture"   # comprend + dessine
```

## État honnête

- **La main est certifiée** (couverture & précision 1.000) ; le cheval/maison sont reconnus
  par CLIP (~0,9+) ; le modèle **comprend la demande** (FR/EN, synonymes : testé 14/14).
- **Étape récupération** : le modèle dessine parmi un corpus de sujets réels et mappe toute
  demande au plus proche. Il ne génère pas encore un dessin inédit pour un sujet jamais vu.
- **Garde anti-triche à finir** : l'optimiseur CLIP peut dériver vers des artefacts
  adversariaux (un « poisson » que CLIP adore mais visuellement faux). On ne garde au corpus
  que les dessins **vérifiés à l'œil**. Prochaine étape : un prior structurel sur l'optimiseur,
  puis grossir le corpus et distiller un modèle génératif `demande → programme`.

## Licence

Usage personnel / recherche.
