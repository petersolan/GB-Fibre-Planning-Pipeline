# 4. Gigabit coverage per address is treated as a probability

Status: accepted (2026-10-07)

## Context

Ofcom publishes coverage as the share of premises in a postcode with gigabit
service, not which premises have it. A postcode at 75% does not say which
addresses are among the 25%.

## Decision

Each address gets `p_no_gigabit = 1 - postcode gigabit share`. Counts of
premises and people without gigabit are expected values (sums of those
probabilities), and road links are ranked by expected people without
gigabit per km of road.

## Consequences

- Totals per postcode, road link and area are unbiased, while individual
  addresses are never labelled as having or lacking service.
- Outputs are fractional (e.g. 12,023.0 people) and are documented as
  estimates.
- Road length is a proxy for build cost: it ignores existing ducts and poles,
  which open data does not provide.
