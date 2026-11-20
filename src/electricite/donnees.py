"""Téléchargement et lecture des trois sources publiques du projet.

- Consommation nationale d'électricité : RTE, éCO2mix, données consolidées et définitives, publiées sur l'open
  data des réseaux énergies (ODRE). Licence Ouverte (Etalab).
- Températures journalières de huit grandes villes : archive d'Open-Meteo. CC BY 4.0.
- Prix spot (day-ahead) de la zone France : Energy-Charts (Fraunhofer ISE), données Bundesnetzagentur / SMARD.
  CC BY 4.0. Pas horaire jusqu'au 30 septembre 2025, quart d'heure depuis le 1er octobre 2025.

Les fichiers bruts vont dans `data/`, qui n'est pas versionné : `uv run python scripts/telecharger.py` les recrée.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

FUSEAU = "Europe/Paris"

URL_CONSOMMATION = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-national-cons-def/exports/csv"
    "?select=date%2Cavg(consommation)%20as%20consommation_mw&group_by=date&order_by=date&limit=-1"
)

VILLES = {
    "Paris": (48.85, 2.35),
    "Lyon": (45.76, 4.84),
    "Marseille": (43.30, 5.37),
    "Lille": (50.63, 3.06),
    "Toulouse": (43.60, 1.44),
    "Bordeaux": (44.84, -0.58),
    "Nantes": (47.22, -1.55),
    "Strasbourg": (48.57, 7.75),
}


def url_temperatures(debut: str, fin: str) -> str:
    lat = ",".join(str(v[0]) for v in VILLES.values())
    lon = ",".join(str(v[1]) for v in VILLES.values())
    return (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
        f"&start_date={debut}&end_date={fin}&daily=temperature_2m_mean&timezone=Europe%2FParis&format=csv"
    )


def url_prix(debut: str, fin: str) -> str:
    return f"https://api.energy-charts.info/price?bzn=FR&start={debut}&end={fin}"


def _telecharger(url: str, chemin: Path, essais: int = 3, pause_s: float = 8.0) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    derniere_erreur: Exception | None = None
    for _ in range(essais):
        try:
            with urllib.request.urlopen(url, timeout=180) as reponse:
                chemin.write_bytes(reponse.read())
            return
        except Exception as erreur:  # réseau ou API momentanément indisponible
            derniere_erreur = erreur
            time.sleep(pause_s)
    raise RuntimeError(f"téléchargement impossible : {url}") from derniere_erreur


def telecharger_tout(dossier: str | Path = "data", annees_prix: range = range(2015, 2027),
                     fin_prix: str = "2026-11-20", debut_temp: str = "2013-01-01",
                     fin_temp: str = "2024-12-31") -> None:
    dossier = Path(dossier)
    _telecharger(URL_CONSOMMATION, dossier / "conso_rte.csv")
    _telecharger(url_temperatures(debut_temp, fin_temp), dossier / "temperatures.csv")
    for annee in annees_prix:
        fin = fin_prix if str(annee) == fin_prix[:4] else f"{annee}-12-31"
        _telecharger(url_prix(f"{annee}-01-01", fin), dossier / "prix" / f"prix_FR_{annee}.json")
        time.sleep(3)


def lire_consommation(dossier: str | Path = "data") -> pd.Series:
    """Consommation moyenne de chaque jour, en GW, indexée par la date."""
    df = pd.read_csv(Path(dossier) / "conso_rte.csv", sep=";", encoding="utf-8-sig", parse_dates=["date"])
    return (df.set_index("date")["consommation_mw"] / 1000).rename("conso").sort_index()


def lire_temperature_france(dossier: str | Path = "data") -> pd.Series:
    """Température moyenne de chaque jour, moyenne simple des huit villes, en °C."""
    df = pd.read_csv(Path(dossier) / "temperatures.csv", skiprows=len(VILLES) + 2)
    df = df.rename(columns={"time": "date", "temperature_2m_mean (°C)": "temperature"})
    df["date"] = pd.to_datetime(df["date"])
    return df.groupby("date")["temperature"].mean().rename("temperature")


def lire_prix(dossier: str | Path = "data") -> pd.Series:
    """Prix spot France en €/MWh, à leur pas d'origine, indexés en heure de Paris (début de chaque pas)."""
    morceaux = []
    for fichier in sorted((Path(dossier) / "prix").glob("prix_FR_*.json")):
        brut = json.loads(fichier.read_text())
        index = pd.to_datetime(brut["unix_seconds"], unit="s", utc=True).tz_convert(FUSEAU)
        morceaux.append(pd.Series(brut["price"], index=index, dtype="float64"))
    prix = pd.concat(morceaux).sort_index()
    return prix[~prix.index.duplicated(keep="first")].rename("prix")
