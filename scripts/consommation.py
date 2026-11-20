"""Partie A : la consommation française et la température.

Écrit resultats/consommation.json et trois figures dans figures/.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from electricite.consommation import (balayage_seuil, construire_variables, ecarts, estimer, resume_par_annee,
                                      walk_forward)
from electricite.donnees import lire_consommation, lire_temperature_france

FIGURES, RESULTATS = Path("figures"), Path("resultats")


def main() -> None:
    FIGURES.mkdir(exist_ok=True)
    RESULTATS.mkdir(exist_ok=True)
    conso, temperature = lire_consommation(), lire_temperature_france()
    df = construire_variables(conso, temperature)

    # 1. Modèle principal : estimé sur 2013-2021, jugé sur 2022-2024
    modele = estimer(df, range(2013, 2022))
    test = ecarts(modele, df[df["annee"] >= 2022])
    par_annee = resume_par_annee(test)

    # 2. Walk-forward : chaque année prévue par un modèle estimé sur les années d'avant
    wf = walk_forward(df, 2016, 2024)

    # 3. D'où vient le seuil de 15 °C : ajustement sur l'apprentissage pour plusieurs seuils
    seuils = balayage_seuil(conso, temperature, range(2013, 2022), [12, 13, 14, 15, 16, 17, 18])

    # Figure A1 : nuage consommation / température, avec la courbe du modèle un mardi ordinaire hors août
    t = np.linspace(df["temperature"].min(), df["temperature"].max(), 200)
    p = modele.params
    courbe = (p["Intercept"] + p["C(jour)[T.1]"] + p["dj_chauffage"] * np.clip(15 - t, 0, None)
              + p["dj_clim"] * np.clip(t - 22, 0, None))
    plt.figure(figsize=(8, 5))
    plt.scatter(df["temperature"], df["conso"], s=3, alpha=0.25, label="un point = un jour, 2013-2024")
    plt.plot(t, courbe, color="black", lw=2, label="modèle, un mardi ordinaire")
    plt.xlabel("Température moyenne du jour (°C), moyenne de 8 grandes villes")
    plt.ylabel("Consommation moyenne du jour (GW)")
    plt.title("France : consommation d'électricité et température")
    plt.legend()
    plt.savefig(FIGURES / "A1_conso_temperature.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure A2 : écart moyen de prévision par année (walk-forward)
    couleurs = ["#c0392b" if e < -2 else "#7f8c8d" for e in wf["ecart_moyen_pct"]]
    plt.figure(figsize=(8, 4.5))
    plt.bar(wf.index.astype(str), wf["ecart_moyen_pct"], color=couleurs)
    plt.axhline(0, color="black", lw=0.8)
    plt.ylim(wf["ecart_moyen_pct"].min() - 1.2, max(wf["ecart_moyen_pct"].max(), 0) + 1.0)
    plt.ylabel("Réalisé − prévu (% du prévu)")
    plt.title("Écart moyen de prévision, chaque année prévue par les années précédentes")
    for annee, e in wf["ecart_moyen_pct"].items():
        plt.text(str(annee), e + (0.25 if e >= 0 else -0.5), f"{e:+.1f}", ha="center", fontsize=9)
    plt.savefig(FIGURES / "A2_ecart_par_annee.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure A3 : consommation mensuelle réalisée et prévue, 2022-2024
    mensuel = test.resample("MS").mean()
    plt.figure(figsize=(9, 4.5))
    plt.plot(mensuel.index, mensuel["conso"], marker="o", label="réalisé")
    plt.plot(mensuel.index, mensuel["prevision"], marker="o", label="prévu par le modèle 2013-2021")
    plt.ylabel("Consommation moyenne (GW)")
    plt.title("2022-2024 : le modèle estimé avant la crise prévoit trop")
    plt.legend()
    plt.savefig(FIGURES / "A3_prevision_2022_2024.png", dpi=150, bbox_inches="tight")
    plt.close()

    resultats = {
        "periode": [str(df.index.min().date()), str(df.index.max().date())],
        "jours": int(len(df)),
        "modele_2013_2021": {
            "r2": round(float(modele.rsquared), 3),
            "coefficients_gw": {k: round(float(v), 2) for k, v in modele.params.items()},
        },
        "test_2022_2024": {int(a): {k: round(float(v), 2) for k, v in r.items()} for a, r in par_annee.iterrows()},
        "walk_forward": {int(a): {k: (round(float(v), 2) if not isinstance(v, str) else v) for k, v in r.items()}
                         for a, r in wf.iterrows()},
        "balayage_seuil": {float(s): {k: round(float(v), 4) for k, v in r.items()} for s, r in seuils.iterrows()},
    }
    (RESULTATS / "consommation.json").write_text(json.dumps(resultats, indent=2, ensure_ascii=False))

    print(f"Modèle 2013-2021 : R² {modele.rsquared:.3f}, {modele.params['dj_chauffage']:.2f} GW par degré de froid")
    print("Test hors échantillon :")
    print(par_annee.round(1).to_string())
    print("Walk-forward :")
    print(wf.round(2).to_string())
    print("Seuil de chauffage (R² sur 2013-2021) :")
    print(seuils.round(4).to_string())


if __name__ == "__main__":
    main()
