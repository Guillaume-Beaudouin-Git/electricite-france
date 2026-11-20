import numpy as np
import pandas as pd
import pytest

from electricite.consommation import construire_variables, walk_forward


def _jeu_fictif():
    jours = pd.date_range("2013-01-01", "2016-12-31", freq="D")
    rng = np.random.default_rng(0)
    temperature = pd.Series(12 + 13 * np.sin(np.arange(len(jours)) * 2 * np.pi / 365.25), index=jours)  # de −1 à 25 °C
    # une consommation qui suit exactement la forme du modèle, plus un bruit
    conso = 45 + 2.0 * (15 - temperature).clip(lower=0) + rng.normal(0, 0.5, len(jours))
    return pd.Series(conso, index=jours), temperature


def test_degres_jours():
    jours = pd.to_datetime(["2024-01-10", "2024-07-10", "2024-05-10"])
    df = construire_variables(pd.Series([60.0, 45.0, 48.0], index=jours), pd.Series([10.0, 25.0, 18.0], index=jours))
    assert df["dj_chauffage"].tolist() == [5.0, 0.0, 0.0]
    assert df["dj_clim"].tolist() == [0.0, 3.0, 0.0]


def test_jours_feries_et_semaine():
    jours = pd.to_datetime(["2024-07-14", "2024-07-15", "2024-12-25"])
    df = construire_variables(pd.Series([40.0, 45.0, 50.0], index=jours), pd.Series([20.0, 20.0, 5.0], index=jours))
    assert df["ferie"].tolist() == [1, 0, 1]
    assert df["jour"].tolist() == ["6", "0", "2"]  # dimanche, lundi, mercredi
    assert df["fin_annee"].tolist() == [0, 0, 1]


def test_walk_forward_n_utilise_que_le_passe():
    conso, temperature = _jeu_fictif()
    df = construire_variables(conso, temperature)
    wf = walk_forward(df, 2015, 2016)
    assert wf.loc[2015, "apprentissage"] == "2013-2014"
    assert wf.loc[2016, "apprentissage"] == "2013-2015"
    # sur des données qui suivent le modèle, on retrouve le gradient et une erreur faible
    assert wf["gradient_gw_par_degre"].tolist() == pytest.approx([2.0, 2.0], abs=0.05)
    assert (wf["erreur_absolue_moyenne_pct"] < 2).all()
