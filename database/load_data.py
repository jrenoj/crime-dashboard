import pandas as pd
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://jrenoj@localhost/la_crime"
CSV_FILE = "data/processed/processed.csv"

engine = create_engine(DATABASE_URL)

chunksize = 5_000
total_loaded = 0

for chunk in pd.read_csv(CSV_FILE, chunksize=chunksize):

    chunk = chunk.rename(columns={
        "DR_NO": "dr_no",
        "DATE OCC": "date_occ",
        "AREA NAME": "area_name",
        "Crm Cd Desc": "crime_description",
        "Vict Age": "victim_age",
        "Vict Sex": "victim_sex",
        "Vict Descent": "victim_descent",
        "LAT": "latitude",
        "LON": "longitude",
        "Year": "year",
        "Month": "month",
        "Day": "day",
        "Time": "time"
    })

    chunk["date_occ"] = pd.to_datetime(chunk["date_occ"])
    chunk["time"] = pd.to_datetime(
        chunk["time"],
        format="%H:%M"
    ).dt.time

    chunk.to_sql(
        "crime_incidents",
        engine,
        if_exists="append",
        index=False,
        method="multi"
    )

    total_loaded += len(chunk)

    print(f"Loaded {total_loaded:,} records")

print("Database loading complete.")