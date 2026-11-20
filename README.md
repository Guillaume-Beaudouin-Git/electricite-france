# Électricité en France : consommation, température et valeur d'une batterie

Deux questions, traitées sur données publiques :

1. **Un modèle simple de la consommation française tient-il hors échantillon, et quand se trompe-t-il ?**
2. **Combien aurait rapporté une batterie en arbitrage sur le prix spot, et quelle part de ce revenu tient à la
   connaissance des prix à l'avance ?**

## Résultats

### Consommation et température (2013-2024)

Régression linéaire de la consommation journalière sur les degrés-jours de chauffage (sous 15 °C) et de
climatisation (au-dessus de 22 °C), le jour de la semaine, les jours fériés, le mois d'août et la fin d'année.

- Estimé sur 2013-2021 : **R² 0,93**, et **2,34 GW de consommation en plus par degré de froid** sous 15 °C.
- Chaque année prévue par un modèle estimé sur les années précédentes (walk-forward) :

| année prévue | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|---|---|
| écart moyen réalisé − prévu | 0,0 % | −0,3 % | +0,1 % | −1,0 % | −4,2 % | −2,3 % | −3,1 % | −5,9 % | −4,2 % |
| erreur absolue moyenne | 3,5 % | 3,6 % | 3,4 % | 3,6 % | 6,6 % | 4,6 % | 4,4 % | 6,4 % | 5,2 % |

  Avant 2020, le modèle n'a pas de biais. Il surestime la consommation en 2020 (confinements), puis durablement
  depuis 2022 : la baisse de consommation qui suit la crise de 2022 n'est pas dans les années d'apprentissage, et
  elle persiste même quand 2022 et 2023 y entrent.
- Le seuil de 15 °C n'est pas posé à la main : c'est celui qui ajuste le mieux l'apprentissage (R² 0,9316, contre
  0,9249 à 14 °C et 0,9308 à 16 °C).

### Batterie en arbitrage sur le prix spot France (2015 – 20 novembre 2026)

Batterie de 1 MW pour 2 MWh, rendement aller-retour 88 %, au plus un cycle par jour. Chaque journée est un
programme linéaire : quand charger, quand décharger, sous les contraintes de puissance, de capacité, de rendement et
de cycle.

| année | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| revenu en prévision parfaite (k€ par MW) | 16,0 | 18,7 | 17,1 | 18,1 | 14,9 | 15,0 | 40,3 | 92,2 | 47,1 | 45,4 | 55,3 | 80,0 |
| part captée en décidant sur les prix de la veille | 70 % | 78 % | 76 % | 74 % | 74 % | 77 % | 77 % | 67 % | 78 % | 77 % | 82 % | 85 % |

\* 2026 : du 1er janvier au 20 novembre (324 jours).

- La « prévision parfaite » est un plafond : elle suppose les prix connus. Décider sur les prix de la veille, aux
  mêmes heures, ne capte que 67 à 85 % de ce plafond. L'écart est la valeur d'une bonne prévision.
- Depuis le 1er octobre 2025, le marché day-ahead européen cote au quart d'heure. Sur les 416 journées qui suivent,
  la même batterie gagne **7,7 % de plus** qu'avec les mêmes prix moyennés à l'heure.
- Sensibilité sur 2024 : deux cycles par jour, +32 % ; batterie de quatre heures (1 MW, 4 MWh), +73 % ; rendement
  de 80 % au lieu de 88 %, −9 %.

## Figures

| | |
|---|---|
| `figures/A1_conso_temperature.png` | consommation contre température, avec la courbe du modèle |
| `figures/A2_ecart_par_annee.png` | écart moyen de prévision par année (walk-forward) |
| `figures/A3_prevision_2022_2024.png` | consommation mensuelle réalisée et prévue, 2022-2024 |
| `figures/B1_revenu_batterie.png` | revenu annuel de la batterie, prévision parfaite et naïve |
| `figures/B2_journee_type.png` | une journée au quart d'heure : prix et état de charge |

## Limites

- **Consommation.** La température est la moyenne simple de huit grandes villes, sans pondération par la
  population. Le modèle ne contient ni prix ni tendance : c'est voulu, pour voir ce que la météo et le calendrier
  expliquent seuls, mais il ne peut pas anticiper une rupture de comportement.
- **Batterie.** Day-ahead seulement : ni marché infrajournalier, ni services système, ni mécanisme de capacité. La
  batterie est preneuse de prix. Pas de frais de réseau ni de coût de vieillissement. La prévision « naïve » est
  volontairement minimale. Le programme linéaire autorise, aux prix négatifs, une charge et une décharge simultanées
  qu'une batterie réelle ne ferait pas ; la limite d'un cycle par jour en borne l'effet.

## Reproduire

```
uv sync --group dev
uv run python scripts/telecharger.py     # environ une minute
uv run python scripts/consommation.py    # partie A, quelques secondes
uv run python scripts/batterie.py        # partie B, une quinzaine de secondes
uv run pytest
```

Les résultats chiffrés sont écrits dans `resultats/`. Les données brutes ne sont pas versionnées.

## Code

| | |
|---|---|
| `src/electricite/donnees.py` | téléchargement et lecture des trois sources |
| `src/electricite/consommation.py` | variables, estimation, test hors échantillon, walk-forward, choix du seuil |
| `src/electricite/batterie.py` | programme linéaire d'une journée, prévision parfaite et naïve, agrégation horaire |
| `tests/` | onze tests sur des cas dont la réponse se calcule à la main |

## Données et licences

- Consommation : RTE, éCO2mix, données consolidées et définitives, via l'open data des réseaux énergies (ODRE).
  Licence Ouverte (Etalab).
- Températures : Open-Meteo, archive historique. CC BY 4.0.
- Prix spot France : Energy-Charts (Fraunhofer ISE), données Bundesnetzagentur / SMARD. CC BY 4.0.

## Comment ce projet a été fait

Le code a été écrit par un agent de programmation IA (Claude Code), sous la direction de l'auteur, Guillaume
Beaudouin. Chaque chiffre de cette page est produit par les scripts ci-dessus et les calculs centraux sont vérifiés
par des tests.
