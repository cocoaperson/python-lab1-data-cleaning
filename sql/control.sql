SELECT COUNT(*) FROM observations;
SELECT s.scientific_name, COUNT(*), AVG(o.height_m)
FROM observations o JOIN deployments d ON d.deployment_pk=o.deployment_pk
JOIN birds b ON b.organism_id=d.organism_id JOIN species s ON s.species_pk=b.species_pk
GROUP BY s.scientific_name ORDER BY s.scientific_name;
SELECT COUNT(*) FROM observations WHERE event_date >= '2014-01-01T00:00:00Z' AND event_date < '2014-01-02T00:00:00Z';
