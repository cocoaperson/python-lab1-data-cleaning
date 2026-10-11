-- datasets определение

CREATE TABLE datasets (
	dataset_pk INTEGER NOT NULL,
	"type" TEXT NOT NULL,
	license TEXT NOT NULL,
	access_rights TEXT NOT NULL,
	institution_code TEXT NOT NULL,
	"language" TEXT NOT NULL,
	rights_holder TEXT NOT NULL,
	dataset_id TEXT NOT NULL,
	dataset_name TEXT NOT NULL,
	owner_institution_code TEXT NOT NULL,
	basis_of_record TEXT NOT NULL,
	information_withheld TEXT NOT NULL,
	sampling_protocol TEXT NOT NULL,
	geodetic_datum TEXT NOT NULL,
	georeference_sources TEXT NOT NULL,
	georeference_verification_status TEXT NOT NULL,
	CONSTRAINT datasets_pk PRIMARY KEY (dataset_pk)
);

CREATE UNIQUE INDEX datasets_dataset_id_IDX ON datasets (dataset_id);


-- species определение

CREATE TABLE species (
	species_pk INTEGER NOT NULL,
	scientific_name VARCHAR(128) NOT NULL,
	vernacular_name VARCHAR(128) NOT NULL,
	kingdom VARCHAR(64) NOT NULL,
	taxon_rank VARCHAR(64) NOT NULL,
	CONSTRAINT species_pk PRIMARY KEY (species_pk)
);

CREATE UNIQUE INDEX species_scientific_name_IDX ON species (scientific_name);


-- birds определение

CREATE TABLE birds (
	organism_name TEXT,
	species_pk INTEGER NOT NULL,
	organism_id VARCHAR(64) NOT NULL,
	sex VARCHAR(16),
	life_stage VARCHAR(32),
	CONSTRAINT birds_pk PRIMARY KEY (organism_id),
	CONSTRAINT birds_species_FK FOREIGN KEY (species_pk) REFERENCES species(species_pk)
);


-- deployments определение

CREATE TABLE deployments (
	deployment_pk INTEGER NOT NULL,
	organism_id VARCHAR(64) NOT NULL,
	device_serial INTEGER NOT NULL,
	catch_location TEXT NOT NULL,
	tracking_start DATE NOT NULL,
	CONSTRAINT deployments_pk PRIMARY KEY (deployment_pk),
	CONSTRAINT deployments_birds_FK FOREIGN KEY (organism_id) REFERENCES birds(organism_id)
);


-- observations определение

CREATE TABLE observations (
	observation_id VARCHAR(64) NOT NULL,
	event_date TEXT NOT NULL,
	elevation_m INTEGER,
	height_m REAL,
	latitude REAL NOT NULL,
	longitude REAL NOT NULL,
	uncertainty_m INTEGER,
	dataset_pk INTEGER NOT NULL,
	deployment_pk INTEGER NOT NULL,
	seconds_since_previous INTEGER,
	CONSTRAINT observations_pk PRIMARY KEY (observation_id),
	CONSTRAINT observations_datasets_FK FOREIGN KEY (dataset_pk) REFERENCES datasets(dataset_pk),
	CONSTRAINT observations_deployments_FK FOREIGN KEY (deployment_pk) REFERENCES deployments(deployment_pk)
);

CREATE INDEX observations_event_date_IDX ON observations (event_date);