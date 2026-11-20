"""Modèle de la consommation journalière : température et calendrier.

La consommation d'électricité en France dépend d'abord du chauffage, donc de la température, puis du calendrier
(jours ouvrés, week-ends, jours fériés, vacances d'été et de fin d'année). Le modèle est une régression linéaire :

    conso = a + b · DJ_chauffage + c · DJ_clim + effets du jour de la semaine + férié + août + fin d'année

où DJ_chauffage = max(0, seuil_chauffage − T) et DJ_clim = max(0, T − seuil_clim) sont des degrés-jours.
Le coefficient b se lit en GW par degré de froid sous le seuil.

Toute évaluation se fait hors échantillon : on estime sur des années passées et on juge sur une année jamais vue.
"""
from __future__ import annotations

import holidays
import pandas as pd
import statsmodels.formula.api as smf

SEUIL_CHAUFFAGE = 15.0
SEUIL_CLIM = 22.0
FORMULE = "conso ~ dj_chauffage + dj_clim + C(jour) + ferie + aout + fin_annee"


def construire_variables(conso: pd.Series, temperature: pd.Series, seuil_chauffage: float = SEUIL_CHAUFFAGE,
                         seuil_clim: float = SEUIL_CLIM) -> pd.DataFrame:
    """Aligne consommation et température sur les jours communs et ajoute les variables du modèle."""
    df = pd.concat([conso.rename("conso"), temperature.rename("temperature")], axis=1, join="inner").copy()
    df["dj_chauffage"] = (seuil_chauffage - df["temperature"]).clip(lower=0)
    df["dj_clim"] = (df["temperature"] - seuil_clim).clip(lower=0)
    df["jour"] = df.index.day_of_week.astype(str)  # "0" = lundi … "6" = dimanche
    annees = range(df.index.year.min(), df.index.year.max() + 1)
    feries = pd.to_datetime(list(holidays.France(years=annees).keys()))
    df["ferie"] = df.index.isin(feries).astype(int)
    df["aout"] = (df.index.month == 8).astype(int)
    df["fin_annee"] = (((df.index.month == 12) & (df.index.day >= 24))
                       | ((df.index.month == 1) & (df.index.day <= 1))).astype(int)
    df["annee"] = df.index.year
    return df


def estimer(df: pd.DataFrame, annees_apprentissage) -> "smf.ols":
    """Régression linéaire (moindres carrés) estimée sur les seules années d'apprentissage."""
    apprentissage = df[df["annee"].isin(list(annees_apprentissage))]
    return smf.ols(FORMULE, data=apprentissage).fit()


def ecarts(modele, df: pd.DataFrame) -> pd.DataFrame:
    """Prévision du modèle et écart relatif (réalisé − prévu) / prévu, jour par jour."""
    sortie = df[["conso"]].copy()
    sortie["prevision"] = modele.predict(df)
    sortie["ecart_pct"] = 100 * (sortie["conso"] - sortie["prevision"]) / sortie["prevision"]
    return sortie


def resume_par_annee(ecarts_jour: pd.DataFrame) -> pd.DataFrame:
    """Erreur absolue moyenne (%) et écart moyen (%) par année."""
    g = ecarts_jour.groupby(ecarts_jour.index.year)
    return pd.DataFrame({
        "erreur_absolue_moyenne_pct": g["ecart_pct"].apply(lambda e: e.abs().mean()),
        "ecart_moyen_pct": g["ecart_pct"].mean(),
        "jours": g.size(),
    }).rename_axis("annee")


def walk_forward(df: pd.DataFrame, premiere_annee_test: int, derniere_annee_test: int) -> pd.DataFrame:
    """Pour chaque année Y : estimation sur toutes les années avant Y, test sur Y seule.

    C'est la façon honnête de mesurer une erreur de prévision : le modèle ne voit jamais l'année qu'il prévoit.
    """
    premiere = int(df["annee"].min())
    lignes = []
    for annee in range(premiere_annee_test, derniere_annee_test + 1):
        modele = estimer(df, range(premiere, annee))
        e = ecarts(modele, df[df["annee"] == annee])
        lignes.append({
            "annee": annee,
            "apprentissage": f"{premiere}-{annee - 1}",
            "erreur_absolue_moyenne_pct": e["ecart_pct"].abs().mean(),
            "ecart_moyen_pct": e["ecart_pct"].mean(),
            "gradient_gw_par_degre": modele.params["dj_chauffage"],
        })
    return pd.DataFrame(lignes).set_index("annee")


def balayage_seuil(conso: pd.Series, temperature: pd.Series, annees_apprentissage, seuils) -> pd.DataFrame:
    """R² du modèle, sur l'apprentissage seulement, pour plusieurs seuils de chauffage."""
    lignes = []
    for seuil in seuils:
        df = construire_variables(conso, temperature, seuil_chauffage=seuil)
        modele = estimer(df, annees_apprentissage)
        lignes.append({"seuil_chauffage": seuil, "r2": modele.rsquared,
                       "gradient_gw_par_degre": modele.params["dj_chauffage"]})
    return pd.DataFrame(lignes).set_index("seuil_chauffage")
