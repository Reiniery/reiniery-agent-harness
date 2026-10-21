---
name: themis-density
description: Use for THEMIS THA/THD/THE density coverage, UTC interval summaries, plasmapause region comparisons, and sampling gaps.
---

Describe the dataset first; identify synthetic demo versus real local data.
Density is cm^-3. Spacecraft IDs: 1 THA, 4 THD, 5 THE.
Plasmapause flag 0 means inside, 1 outside. It is not a quality flag.
Use timezone-bearing ISO-8601 times; intervals are [start,end).
Queries use Unix time in column 1. Report calendar-column mismatches to the owner.
Summarize one spacecraft at a time; choose all/inside/outside explicitly.
Finite positive densities enter sample-weighted statistics; no interpolation.
Gap analysis always uses all regions, so region selection is not mistaken for missing data.
Default cadence is 300 seconds, tolerance 1.5; inspect actual cadence before changing it.
Gaps may reflect source selection rather than instrument downtime.
Do not infer spatial reconstructions from spacecraft sample averages.
