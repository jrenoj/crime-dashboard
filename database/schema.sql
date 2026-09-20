CREATE TABLE IF NOT EXISTS crime_incidents (
    dr_no BIGINT PRIMARY KEY,
    date_occ TIMESTAMP NOT NULL,
    area_name VARCHAR(100) NOT NULL,
    crime_description TEXT NOT NULL,
    victim_age INTEGER,
    victim_sex VARCHAR(10),
    victim_descent VARCHAR(10),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    year INTEGER NOT NULL,
    month VARCHAR(20) NOT NULL,
    day VARCHAR(20) NOT NULL,
    time TIME NOT NULL
);