from database import query_database

result = query_database("""
    SELECT COUNT(*) AS total_records
    FROM crime_incidents;
""")

print(result)
