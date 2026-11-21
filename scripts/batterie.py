"""Partie B : ce qu'aurait rapporté une batterie en arbitrage sur le prix day-ahead français.

Batterie de référence : 1 MW, 2 MWh (deux heures), rendement aller-retour 88 %, un cycle par jour.
Écrit resultats/batterie_annuelle.csv, resultats/batterie.json et deux figures dans figures/.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from electricite.batterie import Batterie, agreger_horaire, optimiser_journee, revenus_journaliers
from electricite.donnees import lire_prix

FIGURES, RESULTATS = Path("figures"), Path("resultats")
DEBUT_QUART_HEURE = "2025-10-01"
PREVISIONS = ["moyenne7_eur", "naif_eur"]
# une teinte, du plus clair au plus foncé : plus la batterie sait des prix, plus la barre est foncée
BLEU_CLAIR, BLEU, BLEU_FONCE, ENCRE = "#86b6ef", "#2a78d6", "#104281", "#1a1a19"


def par_annee(jours: pd.DataFrame) -> pd.DataFrame:
    g = jours.groupby(jours.index.year)
    commun = jours.dropna(subset=PREVISIONS)  # les deux prévisions sont comparées sur les mêmes journées
    gc = commun.groupby(commun.index.year)
    return pd.DataFrame({
        "jours": g.size(),
        "revenu_parfait_eur": g["parfait_eur"].sum(),
        "revenu_parfait_eur_par_jour": g["parfait_eur"].mean(),
        "jours_compares": gc.size(),
        "part_captee_moyenne_7_jours": gc["moyenne7_eur"].sum() / gc["parfait_eur"].sum(),
        "part_captee_veille": gc["naif_eur"].sum() / gc["parfait_eur"].sum(),
        "ecart_max_min_moyen_eur_mwh": g["ecart_max_min_eur_mwh"].mean(),
    }).rename_axis("annee")


def figure_revenus(annuel: pd.DataFrame, premier: pd.Timestamp, dernier: pd.Timestamp) -> None:
    x, w = np.arange(len(annuel)), 0.28
    parfait = annuel["revenu_parfait_eur"] / 1000
    fig, ax = plt.subplots(figsize=(10, 4.8))
    for decalage, hauteur, couleur, nom in [
        (-w, parfait * annuel["part_captee_veille"], BLEU_CLAIR, "planning sur les prix de la veille"),
        (0, parfait * annuel["part_captee_moyenne_7_jours"], BLEU, "planning sur la moyenne des 7 derniers jours"),
        (w, parfait, BLEU_FONCE, "prix connus à l'avance (plafond)"),
    ]:
        ax.bar(x + decalage, hauteur, w, color=couleur, edgecolor="white", linewidth=1, label=nom, zorder=2)
    etiquettes = [str(a) for a in annuel.index]
    etiquettes[0], etiquettes[-1] = etiquettes[0] + "*", etiquettes[-1] + "*"
    ax.set_xticks(x, etiquettes)
    ax.set_ylabel("Revenu (k€ par MW et par an)")
    ax.set_title("Batterie 1 MW / 2 MWh sur le day-ahead France : revenu selon ce qu'elle sait des prix")
    ax.grid(axis="y", color="#e5e5e3", zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    fig.text(0.01, -0.02, f"* année partielle : {annuel.index[0]} à partir du {premier:%d/%m}, {annuel.index[-1]} "
                          f"jusqu'au {dernier:%d/%m}. Prévisions : plafond × part du plafond captée sur les journées "
                          f"où les deux prévisions existent.",
             fontsize=8, color="#555555")
    plt.savefig(FIGURES / "B1_revenu_batterie.png", dpi=150, bbox_inches="tight")
    plt.close()


def figure_journee(prix: pd.Series, b: Batterie, jour: str) -> None:
    debut = pd.Timestamp(jour, tz="Europe/Paris")
    p = prix[(prix.index >= debut) & (prix.index < debut + pd.Timedelta(days=1))]
    if len(p) != 96:
        return
    revenu, _, _, s = optimiser_journee(p.to_numpy(), 0.25, b)
    heures = p.index.hour + p.index.minute / 60
    fig, (haut, bas) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True, height_ratios=[3, 2])
    haut.step(heures, p.to_numpy(), where="post", color=ENCRE, lw=1.5)
    haut.set_ylabel("Prix (€/MWh)")
    haut.set_title(f"{debut:%d/%m/%Y}, prix au quart d'heure : la batterie charge au creux, décharge au pic "
                   f"({revenu:.0f} €)")
    bas.fill_between(heures, s, step="post", color=BLEU, alpha=0.35, lw=0)
    bas.step(heures, s, where="post", color=BLEU, lw=1.5)
    bas.set_ylabel("État de charge (MWh)")
    bas.set_xlabel("Heure (Paris)")
    for ax in (haut, bas):
        ax.grid(axis="y", color="#e5e5e3")
        ax.spines[["top", "right"]].set_visible(False)
    plt.savefig(FIGURES / "B2_journee_type.png", dpi=150, bbox_inches="tight")
    plt.close()


def gain_quart_heure(j15: pd.DataFrame, jh: pd.DataFrame, colonne: str) -> dict:
    """Revenu au quart d'heure contre revenu sur les mêmes prix moyennés à l'heure, sur les journées communes."""
    communs = j15.index.intersection(jh.index)
    ok = communs[j15.loc[communs, colonne].notna().to_numpy() & jh.loc[communs, colonne].notna().to_numpy()]
    return {"jours": int(len(ok)),
            "gain_pct": round(float(100 * (j15.loc[ok, colonne].sum() / jh.loc[ok, colonne].sum() - 1)), 1)}


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTATS.mkdir(exist_ok=True)
    prix = lire_prix()
    b = Batterie()

    jours = revenus_journaliers(prix, b)
    annuel = par_annee(jours)
    annuel.round(3).to_csv(RESULTATS / "batterie_annuelle.csv")
    commun = jours.dropna(subset=PREVISIONS)
    c24 = commun[commun.index.year == 2024]

    # Quart d'heure contre heure, depuis le 1er octobre 2025, sur les mêmes journées
    quart = prix[prix.index >= pd.Timestamp(DEBUT_QUART_HEURE, tz="Europe/Paris")]
    j15 = revenus_journaliers(quart, b)
    jh = revenus_journaliers(agreger_horaire(quart), b)
    communs = j15.index.intersection(jh.index)
    gain_par_annee = {int(a): round(float(100 * (j15.loc[communs[communs.year == a], "parfait_eur"].sum()
                                                 / jh.loc[communs[communs.year == a], "parfait_eur"].sum() - 1)), 1)
                      for a in sorted(set(communs.year))}

    # Sensibilité sur 2024, en prévision parfaite
    p_ref = prix[prix.index.year == 2024]
    sensibilite, reference = {}, None
    for nom, variante in {
        "reference_1MW_2MWh_1cycle": b,
        "2_cycles_par_jour": Batterie(cycles_par_jour=2.0),
        "4_heures_1MW_4MWh": Batterie(energie_mwh=4.0),
        "rendement_80_pct": Batterie(rendement_aller_retour=0.80),
    }.items():
        j = revenus_journaliers(p_ref, variante)
        revenu = float(j["parfait_eur"].sum())
        reference = reference or revenu
        sensibilite[nom] = {"revenu_parfait_eur": round(revenu),
                            "ecart_a_la_reference_pct": round(100 * (revenu / reference - 1), 1),
                            "journees_avec_achat_et_vente_simultanes": int((j["pas_simultanes"] > 0).sum())}

    figure_revenus(annuel, jours.index.min(), jours.index.max())
    figure_journee(prix, b, "2026-03-18")

    resultats = {
        "batterie": {"puissance_mw": b.puissance_mw, "energie_mwh": b.energie_mwh,
                     "rendement_aller_retour": b.rendement_aller_retour, "cycles_par_jour": b.cycles_par_jour},
        "periode": [str(jours.index.min().date()), str(jours.index.max().date())],
        "jours_calcules": int(len(jours)),
        "journees_avec_achat_et_vente_simultanes": int((jours["pas_simultanes"] > 0).sum()),
        "par_annee": {int(a): {k: round(float(v), 3) for k, v in r.items()} for a, r in annuel.iterrows()},
        "ensemble_des_annees": {
            "jours_compares": int(len(commun)),
            "part_captee_moyenne_7_jours": round(float(commun["moyenne7_eur"].sum() / commun["parfait_eur"].sum()), 3),
            "part_captee_veille": round(float(commun["naif_eur"].sum() / commun["parfait_eur"].sum()), 3),
        },
        "gain_moyenne_7_jours_sur_veille_2024_eur": round(float(c24["moyenne7_eur"].sum() - c24["naif_eur"].sum())),
        "quart_heure_contre_heure": {
            "periode": [str(communs.min().date()), str(communs.max().date())],
            "jours": int(len(communs)),
            "revenu_quart_heure_parfait_eur": round(float(j15.loc[communs, "parfait_eur"].sum())),
            "revenu_horaire_parfait_eur": round(float(jh.loc[communs, "parfait_eur"].sum())),
            "prevision_parfaite": gain_quart_heure(j15, jh, "parfait_eur"),
            "moyenne_7_jours": gain_quart_heure(j15, jh, "moyenne7_eur"),
            "veille": gain_quart_heure(j15, jh, "naif_eur"),
            "prevision_parfaite_gain_pct_par_annee": gain_par_annee,
        },
        "sensibilite_2024_prevision_parfaite": sensibilite,
    }
    (RESULTATS / "batterie.json").write_text(json.dumps(resultats, indent=2, ensure_ascii=False))

    print(annuel.round(3).to_string())
    for cle in ["journees_avec_achat_et_vente_simultanes", "ensemble_des_annees",
                "gain_moyenne_7_jours_sur_veille_2024_eur", "quart_heure_contre_heure",
                "sensibilite_2024_prevision_parfaite"]:
        print(cle, ":", resultats[cle])


if __name__ == "__main__":
    main()
