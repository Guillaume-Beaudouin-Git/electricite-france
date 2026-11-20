"""Télécharge les trois sources publiques dans data/ (environ une minute)."""
from electricite.donnees import telecharger_tout

if __name__ == "__main__":
    telecharger_tout("data")
    print("Données téléchargées dans data/")
