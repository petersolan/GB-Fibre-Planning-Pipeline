# 5. Route new cable from the existing gigabit network with pgRouting

Status: accepted (2026-10-08)

## Context

Ranking streets by people without gigabit per km of their own length treats
every street as if cable were already at its end. In reality cable has to be
brought to it, and a cheap street at the end of a long run is not cheap.
Exchange and cabinet locations are not open data, and neither are Openreach's
duct and pole maps.

## Decision

- Build a graph from OS Open Roads: links as edges, their `startNode` /
  `endNode` junctions as vertices, cost = length × a road-type multiplier
  (A road 3, B road 2, minor road 1.2, local roads 1; in
  `conf/base/parameters.yml`).
- Treat road links whose premises all have gigabit as the **existing
  network**: new cable can start at any of their junctions.
- Join a virtual super-source (vertex 0) to every existing-network junction
  at zero cost and run **one** `pgr_dijkstra` from it to both junctions of
  every gap street: a multi-source shortest path in a single query.
- Each gap street connects at its cheaper junction. Its total build is
  connection length + street length, and gap streets are ranked by people
  without gigabit per km of that total.
- The union of all chosen routes is the proposed build network
  (`fibre.build_route`), in which shared routes count once.

## Consequences

- Rankings now reflect reach: 6 of the previous top 20 streets drop out, and
  isolated streets fall furthest.
- The build network is a shortest-path tree, not an optimal Steiner tree, so
  total cable is an upper bound: connecting one street can make a neighbour
  cheaper, which the ranking does not re-evaluate.
- Costs are relative, not money: there is no data on existing ducts, poles or
  wayleaves, which dominate real costs.
- Needs the pgRouting extension, so PostGIS runs from the
  `pgrouting/pgrouting` image (same PostgreSQL 17 / PostGIS 3.5 base), in
  Docker Compose and in CI.
