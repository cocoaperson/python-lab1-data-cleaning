-- gui_lab.species определение

-- Drop table

-- DROP TABLE gui_lab.species;

CREATE TABLE gui_lab.species (
	species_pk int4 NOT NULL,
	scientific_name varchar(128) NOT NULL,
	vernacular_name varchar(128) NOT NULL,
	kingdom varchar(64) NOT NULL,
	taxon_rank varchar(64) NOT NULL,
	CONSTRAINT species_pkey PRIMARY KEY (species_pk),
	CONSTRAINT species_scientific_name_key UNIQUE (scientific_name)
);


-- gui_lab.datasets определение

-- Drop table

-- DROP TABLE gui_lab.datasets;

CREATE TABLE gui_lab.datasets (
	dataset_pk int4 NOT NULL,
	"type" text NOT NULL,
	"language" text NOT NULL,
	license text NOT NULL,
	rights_holder text NOT NULL,
	access_rights text NOT NULL,
	dataset_id text NOT NULL,
	institution_code text NOT NULL,
	dataset_name text NOT NULL,
	owner_institution_code text NOT NULL,
	basis_of_record text NOT NULL,
	information_withheld text NOT NULL,
	sampling_protocol text NOT NULL,
	geodetic_datum text NOT NULL,
	georeference_sources text NOT NULL,
	georeference_verification_status text NOT NULL,
	CONSTRAINT datasets_dataset_id_key UNIQUE (dataset_id),
	CONSTRAINT datasets_pkey PRIMARY KEY (dataset_pk)
);


-- gui_lab.birds определение

-- Drop table

-- DROP TABLE gui_lab.birds;

CREATE TABLE gui_lab.birds (
	organism_id varchar(64) NOT NULL,
	organism_name text NULL,
	sex varchar(16) NULL,
	life_stage varchar(32) NULL,
	species_pk int4 NOT NULL,
	CONSTRAINT birds_pkey PRIMARY KEY (organism_id),
	CONSTRAINT birds_species_fk FOREIGN KEY (species_pk) REFERENCES gui_lab.species(species_pk)
);


-- gui_lab.deployments определение

-- Drop table

-- DROP TABLE gui_lab.deployments;

CREATE TABLE gui_lab.deployments (
	deployment_pk int4 NOT NULL,
	organism_id varchar(64) NOT NULL,
	device_serial int4 NOT NULL,
	catch_location text NOT NULL,
	tracking_start date NOT NULL,
	CONSTRAINT deployments_pkey PRIMARY KEY (deployment_pk),
	CONSTRAINT deployments_birds_fk FOREIGN KEY (organism_id) REFERENCES gui_lab.birds(organism_id)
);


-- gui_lab.observations определение

-- Drop table

-- DROP TABLE gui_lab.observations;

CREATE TABLE gui_lab.observations (
	observation_id varchar(64) NOT NULL,
	event_date timestamptz NOT NULL,
	elevation_m int4 NULL,
	height_m float8 NULL,
	latitude float8 NOT NULL,
	longitude float8 NOT NULL,
	uncertainty_m int4 NULL,
	dataset_pk int4 NOT NULL,
	deployment_pk int4 NOT NULL,
	seconds_since_previous int4 NULL,
	CONSTRAINT observations_latitude_check CHECK (((latitude >= ('-90'::integer)::double precision) AND (latitude <= (90)::double precision))),
	CONSTRAINT observations_longitude_check CHECK (((longitude >= ('-180'::integer)::double precision) AND (longitude <= (180)::double precision))),
	CONSTRAINT observations_pkey PRIMARY KEY (observation_id),
	CONSTRAINT observations_uncertainty_m_check CHECK ((uncertainty_m >= 0)),
	CONSTRAINT observations_datasets_fk FOREIGN KEY (dataset_pk) REFERENCES gui_lab.datasets(dataset_pk),
	CONSTRAINT observations_deployments_fk FOREIGN KEY (deployment_pk) REFERENCES gui_lab.deployments(deployment_pk)
);
CREATE INDEX idx_observations_date ON gui_lab.observations USING btree (event_date);
CREATE INDEX idx_observations_deployment ON gui_lab.observations USING btree (deployment_pk);