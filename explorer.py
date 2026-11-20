import pandas as pd
import matplotlib.pyplot as plt

# 1. Consommation nationale RTE : une ligne par jour, moyenne de la journée en MW
conso = pd.read_csv("data/conso_rte.csv", sep=";", encoding="utf-8-sig", parse_dates=["date"])
conso = conso.set_index("date")

# 2. Températures : huit villes, une ligne par ville et par jour ; les dix premières lignes décrivent les villes
temp = pd.read_csv("data/temperatures.csv", skiprows=10)
temp = temp.rename(columns={"time": "date", "temperature_2m_mean (°C)": "temperature"})
temp["date"] = pd.to_datetime(temp["date"])
temperature_france = temp.groupby("date")["temperature"].mean()

# 3. On aligne les deux séries sur les jours communs
df = conso.join(temperature_france, how="inner")
df["consommation_gw"] = df["consommation_mw"] / 1000
print(df[["consommation_gw", "temperature"]].describe().round(1))
print("Période :", df.index.min().date(), "→", df.index.max().date(), "|", len(df), "jours")

# 4. Le nuage de points : consommation contre température
plt.figure(figsize=(8, 5))
plt.scatter(df["temperature"], df["consommation_gw"], s=3, alpha=0.3)
plt.xlabel("Température moyenne du jour (°C), moyenne de 8 grandes villes")
plt.ylabel("Consommation moyenne du jour (GW)")
plt.title("France : consommation d'électricité et température")
plt.savefig("figures/conso_temperature.png", dpi=150, bbox_inches="tight")
print("Figure enregistrée : figures/conso_temperature.png")