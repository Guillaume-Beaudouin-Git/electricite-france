"""Partie B : ce qu'aurait rapporté une batterie en arbitrage sur le prix spot français.

Batterie de référence : 1 MW, 2 MWh (deux heures), rendement aller-retour 88 %, un cycle par jour.
Écrit resultats/batterie_annuelle.csv, resultats/batterie.json et deux figures dans figures/.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from electricite.batterie import Batterie, agreger_horaire, revenus_journaliers
from electricite.donnees import lire_prix

FIGURES, RESULTATS = Path("figures"), Path("resultats")
DEBUT_QUART_HEURE = "2025-10-01"


def par_annee(jours: pd.DataFrame) -> pd.DataFrame:
    g = jours.groupby(jours.index.year)
    commun = jours.dropna(subset=["naif_eur"])
    gc = commun.groupby(commun.index.year)
    return pd.DataFrame({
        "jours": g.size(),
        "revenu_parfait_eur": g["parfait_eur"].sum(),
        "revenu_parfait_eur_par_jour": g["parfait_eur"].mean(),
        "part_captee_par_la_prevision_naive": gc["naif_eur"].sum() / gc["parfait_eur"].sum(),
        "ecart_max_min_moyen_eur_mwh": g["ecart_max_min_eur_mwh"].mean(),
    }).rename_axis("annee")


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTATS.mkdir(exist_ok=True)
    prix = lire_prix()
    b = Batterie()

    jours = revenus_journaliers(prix, b)
    annuel = par_annee(jours)
    annuel.round(3).to_csv(RESULTATS / "batterie_annuelle.csv")

    # Quart d'heure contre heure, depuis le 1er octobre 2025, sur les mêmes journées
    quart = prix[prix.index >= pd.Timestamp(DEBUT_QUART_HEURE, tz="Europe/Paris")]
    j15 = revenus_journaliers(quart, b)
    jh = revenus_journaliers(agreger_horaire(quart), b)
    communs = j15.index.intersection(jh.index)
    gain_15 = float(j15.loc[communs, "parfait_eur"].sum())
    gain_h = float(jh.loc[communs, "parfait_eur"].sum())

    # Sensibilité : deux cycles par jour, batterie de quatre heures, sur 2024
    annee_ref = 2024
    p_ref = prix[prix.index.year == annee_ref]
    sensibilite = {}
    for nom, variante in {
        "reference_1MW_2MWh_1cycle": b,
        "2_cycles_par_jour": Batterie(cycles_par_jour=2.0),
        "4_heures_1MW_4MWh": Batterie(energie_mwh=4.0),
        "rendement_80_pct": Batterie(rendement_aller_retour=0.80),
    }.items():
        sensibilite[nom] = round(float(revenus_journaliers(p_ref, variante)["parfait_eur"].sum()), 0)

    # Figure B1 : revenu annuel en prévision parfaite, et part captée par la prévision naïve
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(annuel.index.astype(str), annuel["revenu_parfait_eur"] / 1000, color="#2c7fb8", label="prévision parfaite")
    ax.bar(annuel.index.astype(str), annuel["revenu_parfait_eur"] * annuel["part_captee_par_la_prevision_naive"] / 1000,
           color="#a6bddb", label="prévision naïve (prix de la veille)")
    ax.set_ylabel("Revenu annuel (k€ par MW)")
    ax.set_title("Batterie 1 MW / 2 MWh en arbitrage sur le prix spot France")
    ax.legend()
    plt.savefig(FIGURES / "B1_revenu_batterie.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure B2 : une journée type, prix et planning optimal
    from electricite.batterie import optimiser_journee
    exemple = prix[(prix.index >= pd.Timestamp("2026-03-18", tz="Europe/Paris"))
                   & (prix.index < pd.Timestamp("2026-03-19", tz="Europe/Paris"))]
    if len(exemple) == 96:
        revenu, c, d, s = optimiser_journee(exemple.to_numpy(), 0.25, b)
        fig, ax1 = plt.subplots(figsize=(9, 4.5))
        heures = exemple.index.hour + exemple.index.minute / 60
        ax1.step(heures, exemple.to_numpy(), where="post", color="black", label="prix (€/MWh)")
        ax1.set_xlabel("Heure (Paris), 18 mars 2026")
        ax1.set_ylabel("Prix spot (€/MWh)")
        ax2 = ax1.twinx()
        ax2.fill_between(heures, s, step="post", alpha=0.3, color="#2c7fb8", label="état de charge (MWh)")
        ax2.set_ylabel("État de charge (MWh)")
        ax1.set_title(f"Une journée au quart d'heure : la batterie charge au creux, décharge au pic ({revenu:.0f} €)")
        plt.savefig(FIGURES / "B2_journee_type.png", dpi=150, bbox_inches="tight")
        plt.close()

    resultats = {
        "batterie": {"puissance_mw": b.puissance_mw, "energie_mwh": b.energie_mwh,
                     "rendement_aller_retour": b.rendement_aller_retour, "cycles_par_jour": b.cycles_par_jour},
        "jours_calcules": int(len(jours)),
        "par_annee": {int(a): {k: round(float(v), 3) for k, v in r.items()} for a, r in annuel.iterrows()},
        "quart_heure_contre_heure": {
            "periode": [str(communs.min().date()), str(communs.max().date())],
            "jours": int(len(communs)),
            "revenu_quart_heure_eur": round(gain_15, 0),
            "revenu_horaire_eur": round(gain_h, 0),
            "gain_du_quart_heure_pct": round(100 * (gain_15 / gain_h - 1), 1),
        },
        f"sensibilite_{annee_ref}_eur": sensibilite,
    }
    (RESULTATS / "batterie.json").write_text(json.dumps(resultats, indent=2, ensure_ascii=False))

    print(annuel.round(2).to_string())
    print("Quart d'heure contre heure :", resultats["quart_heure_contre_heure"])
    print(f"Sensibilité {annee_ref} :", sensibilite)


if __name__ == "__main__":
    main()
