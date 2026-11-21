"""Arbitrage d'une batterie sur le prix day-ahead français.

Chaque jour, la batterie achète de l'électricité quand elle est bon marché et la revend quand elle est chère.
Le planning optimal d'une journée est un programme linéaire, résolu exactement par HiGHS (scipy.optimize.linprog) :

    maximiser   Σ_t p_t · (d_t − c_t) · Δ                         revenu de la journée (€)
    sous        s_t = s_{t−1} + η · c_t · Δ − d_t · Δ / η            état de charge (MWh), s_{−1} = 0
                s_{T−1} = 0                                          la batterie finit la journée vide
                0 ≤ c_t, d_t ≤ P        0 ≤ s_t ≤ E                  puissance et capacité
                Σ_t d_t · Δ / η ≤ k · E                              au plus k cycles complets par jour

c_t et d_t sont les puissances achetée et revendue au réseau (MW), Δ la durée d'un pas (h), p_t le prix (€/MWh),
η la racine du rendement aller-retour.

Trois stratégies, toutes payées aux prix réalisés :
- « prévision parfaite » : le planning est calculé sur les prix réalisés eux-mêmes. C'est un plafond, inatteignable.
- « moyenne des 7 derniers jours » : le planning est calculé sur le profil de prix moyen des sept journées
  précédentes (au moins cinq journées comparables exigées).
- « veille » : le planning est calculé sur les prix de la veille aux mêmes heures.
L'écart entre une stratégie et le plafond borne ce qu'une meilleure prévision pourrait ajouter.

Le programme linéaire n'interdit pas d'acheter et de revendre au même pas, ce qu'une batterie réelle ne fait pas :
la colonne `pas_simultanes` compte les pas où la solution de la prévision parfaite le fait.

Hypothèses : batterie preneuse de prix (elle ne fait pas bouger le marché), pas de frais de réseau ou de marché, pas
de coût de vieillissement, chaque journée optimisée seule, exécution exacte au prix day-ahead.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog

JOURS_MOYENNE = 7      # la moyenne porte sur les sept journées précédentes…
MIN_JOURS_MOYENNE = 5  # …dont au moins cinq comparables (même nombre de pas, même durée de pas)


@dataclass(frozen=True)
class Batterie:
    puissance_mw: float = 1.0
    energie_mwh: float = 2.0
    rendement_aller_retour: float = 0.88
    cycles_par_jour: float = 1.0

    @property
    def eta(self) -> float:
        return float(np.sqrt(self.rendement_aller_retour))


def optimiser_journee(prix: np.ndarray, pas_h: float, batterie: Batterie = Batterie()):
    """Planning optimal d'une journée. Renvoie (revenu en €, achats c en MW, ventes d en MW, état de charge en MWh)."""
    prix = np.asarray(prix, dtype=float)
    T, eta, P, E = len(prix), batterie.eta, batterie.puissance_mw, batterie.energie_mwh
    # variables x = [c_0 … c_{T−1}, d_0 … d_{T−1}, s_0 … s_{T−1}]
    cout = np.concatenate([prix * pas_h, -prix * pas_h, np.zeros(T)])
    A_eq = np.zeros((T + 1, 3 * T))
    for t in range(T):
        A_eq[t, 2 * T + t] = 1.0                    # s_t
        if t > 0:
            A_eq[t, 2 * T + t - 1] = -1.0           # − s_{t−1}
        A_eq[t, t] = -eta * pas_h                   # − η c_t Δ
        A_eq[t, T + t] = pas_h / eta                # + d_t Δ / η
    A_eq[T, 3 * T - 1] = 1.0                        # s_{T−1} = 0
    b_eq = np.zeros(T + 1)
    A_ub = np.concatenate([np.zeros(T), np.full(T, pas_h / eta), np.zeros(T)])[None, :]
    b_ub = np.array([batterie.cycles_par_jour * E])
    bornes = [(0, P)] * (2 * T) + [(0, E)] * T
    res = linprog(cout, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bornes, method="highs")
    if res.status != 0:
        raise RuntimeError(f"optimisation impossible : {res.message}")
    c, d, s = res.x[:T], res.x[T:2 * T], res.x[2 * T:]
    return float(-res.fun), c, d, s


def revenu_au_prix(prix: np.ndarray, c: np.ndarray, d: np.ndarray, pas_h: float) -> float:
    """Revenu d'un planning (c, d) payé aux prix donnés."""
    return float(np.sum(np.asarray(prix) * (d - c)) * pas_h)


def _planifier_puis_payer(prevision: np.ndarray, realise: np.ndarray, pas_h: float, batterie: Batterie) -> float:
    """Planning calculé sur une prévision des prix, payé aux prix réalisés."""
    _, c, d, _ = optimiser_journee(prevision, pas_h, batterie)
    return revenu_au_prix(realise, c, d, pas_h)


def _journees(prix: pd.Series):
    """Découpe la série en journées de marché (heure de Paris) complètes et régulières : (date, prix, pas en h)."""
    for jour, p in prix.groupby(prix.index.date):
        if p.isna().any() or len(p) < 2:
            continue
        pas = np.unique((p.index[1:] - p.index[:-1]).total_seconds()) / 3600  # en heures
        if len(pas) != 1:
            continue  # pas irrégulier (jour du passage au quart d'heure, trou)
        heures = len(p) * pas[0]
        if heures not in (23.0, 24.0, 25.0):
            continue  # journée incomplète
        yield jour, p.to_numpy(), float(pas[0])


def revenus_journaliers(prix: pd.Series, batterie: Batterie = Batterie()) -> pd.DataFrame:
    """Revenu de chaque journée selon les trois stratégies (NaN quand la prévision n'existe pas ce jour-là)."""
    lignes, passe = [], []  # passe : (date, prix, pas) des journées des sept derniers jours
    for jour, p, pas_h in _journees(prix):
        jour = pd.Timestamp(jour)
        parfait, c, d, _ = optimiser_journee(p, pas_h, batterie)
        # seules les journées de même longueur et de même pas servent de prévision
        comparables = {j: q for j, q, pas in passe if len(q) == len(p) and pas == pas_h}
        veille = comparables.get(jour - pd.Timedelta(days=1))
        semaine = [q for j, q in comparables.items() if 1 <= (jour - j).days <= JOURS_MOYENNE]
        lignes.append({
            "date": jour,
            "pas_h": pas_h,
            "parfait_eur": parfait,
            "moyenne7_eur": (_planifier_puis_payer(np.mean(semaine, axis=0), p, pas_h, batterie)
                             if len(semaine) >= MIN_JOURS_MOYENNE else np.nan),
            "naif_eur": _planifier_puis_payer(veille, p, pas_h, batterie) if veille is not None else np.nan,
            "pas_simultanes": int(np.sum(np.minimum(c, d) > 1e-6)),
            "ecart_max_min_eur_mwh": float(p.max() - p.min()),
        })
        passe = [x for x in passe if (jour - x[0]).days < JOURS_MOYENNE] + [(jour, p, pas_h)]
    return pd.DataFrame(lignes).set_index("date")


def agreger_horaire(prix: pd.Series) -> pd.Series:
    """Moyenne horaire d'une série infra-horaire (heure de Paris)."""
    return prix.resample("1h").mean()
