import os
import pandas as pd
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jrenoj@localhost/la_crime")

engine = create_engine(DATABASE_URL)

def query_database(query, params=None):
    return pd.read_sql(query,engine, params=params)
