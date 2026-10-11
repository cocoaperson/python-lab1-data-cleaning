-- datasets определение

CREATE TABLE datasets (dataset_pk INTEGER PRIMARY KEY,
type TEXT NOT NULL,
language TEXT NOT NULL,
license TEXT NOT NULL,
rights_holder TEXT NOT NULL,
access_rights TEXT NOT NULL,
dataset_id TEXT NOT NULL,
institution_code TEXT NOT NULL,
dataset_name TEXT NOT NULL,
owner_institution_code TEXT NOT NULL,
basis_of_record TEXT NOT NULL,
information_withheld TEXT NOT NULL,
sampling_protocol TEXT NOT NULL,
geodetic_datum TEXT NOT NULL,
georeference_sources TEXT NOT NULL,
georeference_verification_status TEXT NOT NULL,
UNIQUE(dataset_id));
-- species определение

CREATE TABLE species (species_pk INTEGER PRIMARY KEY,
scientific_name VARCHAR(128) NOT NULL UNIQUE,
vernacular_name VARCHAR(128) NOT NULL,
kingdom VARCHAR(64) NOT NULL,
taxon_rank VARCHAR(64) NOT NULL);
-- birds определение

CREATE TABLE birds (organism_id VARCHAR(64) PRIMARY KEY,
organism_name TEXT,
sex VARCHAR(16),
life_stage VARCHAR(32),
species_pk INTEGER NOT NULL REFERENCES species(species_pk));
-- deployments определение

CREATE TABLE deployments (deployment_pk INTEGER PRIMARY KEY,
organism_id VARCHAR(64) NOT NULL REFERENCES birds(organism_id),
device_serial INTEGER NOT NULL,
catch_location TEXT NOT NULL,
tracking_start DATE NOT NULL);
-- observations определение

CREATE TABLE observations (observation_id VARCHAR(64) PRIMARY KEY,
event_date TEXT NOT NULL,
elevation_m INTEGER,
height_m REAL,
latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
uncertainty_m INTEGER CHECK(uncertainty_m >= 0),
dataset_pk INTEGER NOT NULL REFERENCES datasets(dataset_pk),
deployment_pk INTEGER NOT NULL REFERENCES deployments(deployment_pk),
seconds_since_previous INTEGER);

CREATE INDEX idx_observations_date ON
observations(event_date);

CREATE INDEX idx_observations_deployment ON
observations(deployment_pk);
