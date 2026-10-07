# Query performance notes

## Bounding-box search on premises (`GET /v1/premises?bbox=...`)

Premises are stored in British National Grid (EPSG:27700) with a GiST index
on `geom`. API clients send WGS84 bounding boxes. Where the transform goes
decides whether the index can be used.

```sql
-- Used by the API: transform the box once, compare against the indexed column
SELECT uprn FROM fibre.premises
WHERE geom && ST_Transform(ST_MakeEnvelope(-3.535, 50.720, -3.525, 50.727, 4326), 27700);

-- Naive: transform every row, so the index on geom can't be used
SELECT uprn FROM fibre.premises
WHERE ST_Transform(geom, 4326) && ST_MakeEnvelope(-3.535, 50.720, -3.525, 50.727, 4326);
```

`EXPLAIN (ANALYZE)` on Exeter (73,646 premises, 3,674 in the box):

| Query | Plan | Execution time |
|---|---|---|
| Transform the box | Bitmap Index Scan on `ix_premises_geom` | **0.74 ms** |
| Transform every row | Parallel Seq Scan, 35,072 rows removed by filter per worker | 364 ms |

About 490 times faster, and the gap grows with the table: the index scan
reads only the rows in the box, the sequential scan reads them all.

The box is reprojected as a polygon (its edges curve slightly between the
two systems), so `&&` against it is a bounding-box test, which is what this
endpoint promises.

## Database connections: use 127.0.0.1, not localhost

On Windows, `localhost` resolves to IPv6 `::1` first. Docker publishes the
PostGIS port on IPv4 only, so every new connection hung (about 2 minutes
here) before anything happened. The first full pipeline run took 11 minutes;
connecting to `127.0.0.1` brought it to 30 seconds. Timing a connection to
each host showed it: 0.1 s for 127.0.0.1, still hanging after 200 s for
localhost.
