import numpy as np
import pandas as pd
import pytest

from electricite.batterie import Batterie, agreger_horaire, optimiser_journee, revenu_au_prix, revenus_journaliers

SANS_PERTES = Batterie(puissance_mw=1.0, energie_mwh=2.0, rendement_aller_retour=1.0, cycles_par_jour=1.0)


def test_deux_heures_basses_deux_heures_hautes():
    # acheter 2 MWh à 10 €/MWh, revendre 2 MWh à 100 €/MWh : 2 × (100 − 10) = 180 €
    revenu, c, d, s = optimiser_journee(np.array([10, 10, 100, 100]), 1.0, SANS_PERTES)
    assert revenu == pytest.approx(180.0)
    assert c[:2] == pytest.approx([1, 1]) and d[2:] == pytest.approx([1, 1])
    assert s[-1] == pytest.approx(0.0)


def test_prix_plats_rien_a_gagner():
    revenu, *_ = optimiser_journee(np.full(24, 50.0), 1.0, Batterie())
    assert revenu == pytest.approx(0.0, abs=1e-6)


def test_le_rendement_reduit_le_revenu():
    prix = np.array([10, 10, 100, 100])
    sans, *_ = optimiser_journee(prix, 1.0, SANS_PERTES)
    avec, *_ = optimiser_journee(prix, 1.0, Batterie(rendement_aller_retour=0.81))
    assert avec < sans
    # rendement 0,81 : η = 0,9 ; 2 MWh achetés stockent 1,8 MWh, qui rendent 1,62 MWh : 162 − 20 = 142 €
    assert avec == pytest.approx(142.0)


def test_etat_de_charge_dans_les_bornes():
    rng = np.random.default_rng(0)
    prix = rng.normal(60, 30, 96)
    b = Batterie()
    _, c, d, s = optimiser_journee(prix, 0.25, b)
    assert (s >= -1e-9).all() and (s <= b.energie_mwh + 1e-9).all()
    assert (c <= b.puissance_mw + 1e-9).all() and (d <= b.puissance_mw + 1e-9).all()


def test_un_cycle_par_jour_au_plus():
    # deux creux et deux pics : sans limite la batterie ferait deux cycles ; limitée à un cycle, elle n'en fait qu'un
    prix = np.array([10, 10, 100, 100, 10, 10, 100, 100])
    un, *_ = optimiser_journee(prix, 1.0, SANS_PERTES)
    deux, *_ = optimiser_journee(prix, 1.0, Batterie(rendement_aller_retour=1.0, cycles_par_jour=2.0))
    assert un == pytest.approx(180.0)
    assert deux == pytest.approx(360.0)


def test_revenu_au_prix_coherent_avec_l_optimum():
    prix = np.array([10, 10, 100, 100])
    revenu, c, d, _ = optimiser_journee(prix, 1.0, SANS_PERTES)
    assert revenu_au_prix(prix, c, d, 1.0) == pytest.approx(revenu)


def test_prevision_naive_jamais_au_dessus_du_parfait():
    rng = np.random.default_rng(1)
    index = pd.date_range("2024-03-04", periods=24 * 10, freq="h", tz="Europe/Paris")
    profil = 50 + 30 * np.sin(np.arange(len(index)) * 2 * np.pi / 24)
    prix = pd.Series(profil + rng.normal(0, 10, len(index)), index=index)
    jours = revenus_journaliers(prix, Batterie())
    assert len(jours) == 10
    assert jours["naif_eur"].isna().sum() == 1  # le premier jour n'a pas de veille
    assert (jours["naif_eur"].dropna() <= jours["parfait_eur"][jours["naif_eur"].notna()] + 1e-6).all()


@pytest.mark.parametrize("jour, heures", [("2024-03-31", 23), ("2024-10-27", 25)])
def test_journee_de_changement_d_heure(jour, heures):
    # trois journées autour du changement d'heure ; chaque jour, 10 €/MWh les deux premières heures, 100 €/MWh
    # les deux dernières, 50 €/MWh sinon : sans pertes, la batterie gagne 2 × (100 − 10) = 180 € chaque jour
    j = pd.Timestamp(jour)
    debut, fin = (j - pd.Timedelta(days=1)).tz_localize("Europe/Paris"), (j + pd.Timedelta(days=2)).tz_localize(
        "Europe/Paris")  # minuit heure de Paris, la veille et le surlendemain
    prix = pd.Series(50.0, index=pd.date_range(debut, fin, freq="h", inclusive="left"))
    for _, heures_du_jour in prix.groupby(prix.index.date):
        prix.loc[heures_du_jour.index[:2]] = 10.0
        prix.loc[heures_du_jour.index[-2:]] = 100.0
    jours = revenus_journaliers(prix, SANS_PERTES)
    assert (prix.index.date == pd.Timestamp(jour).date()).sum() == heures
    assert len(jours) == 3 and jours["parfait_eur"].tolist() == pytest.approx([180.0] * 3)
    # la journée de 23 ou 25 heures et son lendemain n'ont pas de veille de même longueur
    assert jours["naif_eur"].isna().all()


def test_moyenne_des_sept_jours():
    # dix journées identiques : la moyenne des jours précédents est le prix réalisé, donc elle atteint le plafond,
    # dès qu'il y a cinq journées précédentes
    index = pd.date_range("2024-03-04", periods=24 * 10, freq="h", tz="Europe/Paris")
    prix = pd.Series(50 + 30 * np.sin(np.arange(len(index)) * 2 * np.pi / 24), index=index)
    jours = revenus_journaliers(prix, Batterie())
    assert jours["moyenne7_eur"].isna().sum() == 5
    assert jours["moyenne7_eur"].dropna().tolist() == pytest.approx(jours["parfait_eur"].iloc[5:].tolist())
    assert (jours["pas_simultanes"] == 0).all()


def test_agregation_horaire():
    index = pd.date_range("2025-10-02", periods=8, freq="15min", tz="Europe/Paris")
    prix = pd.Series([1, 2, 3, 4, 10, 20, 30, 40], index=index, dtype=float)
    horaire = agreger_horaire(prix)
    assert horaire.tolist() == pytest.approx([2.5, 25.0])
