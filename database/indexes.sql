CREATE INDEX IF NOT EXISTS idx_crime_year 
ON crime_incidents (year);

CREATE INDEX IF NOT EXISTS idx_crime_area
ON crime_incidents (area_name);

CREATE INDEX IF NOT EXISTS idx_crime_description
ON crime_incidents (crime_description);

CREATE INDEX IF NOT EXISTS idx_crime_date
ON crime_incidents (date_occ);
