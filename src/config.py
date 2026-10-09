from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
INTERIM = ROOT / "data/interim"
PROCESSED = ROOT / "data/processed"
RESULTS = ROOT / "results"
INPUT = RAW / "inbo_gull_gps_tracking_1gb.csv"
CUTOFF = "2026-10-09T23:59:59Z"
SAMPLE_SIZE = 200_000
CATEGORIES = [
    "type",
    "language",
    "license",
    "rightsHolder",
    "accessRights",
    "datasetID",
    "institutionCode",
    "datasetName",
    "ownerInstitutionCode",
    "basisOfRecord",
    "informationWithheld",
    "sex",
    "lifeStage",
    "organismID",
    "samplingProtocol",
    "geodeticDatum",
    "georeferenceSources",
    "georeferenceVerificationStatus",
    "scientificName",
    "kingdom",
    "taxonRank",
    "vernacularName",
]
FLOATS = ["minimumDistanceAboveSurfaceInMeters", "decimalLatitude", "decimalLongitude"]
INTEGERS = ["minimumElevationInMeters", "coordinateUncertaintyInMeters"]
TEXT = ["id", "occurrenceID", "organismName", "dynamicProperties", "samplingEffort"]
SCHEMA = {name: "category" for name in CATEGORIES}
SCHEMA.update({name: "float64" for name in FLOATS})
SCHEMA.update({name: "Int32" for name in INTEGERS})
SCHEMA.update({name: "string[pyarrow]" for name in TEXT})
SCHEMA["eventDate"] = "datetime64[us, UTC]"
