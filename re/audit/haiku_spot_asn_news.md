Warning: no stdin data received in 3s, proceeding without it. If piping from a slow command, redirect stdin explicitly: < /dev/null to skip, or wait longer.
Based on my comprehensive verification of the reverse-engineering claims, here's the analysis:

| Claim | VALID / WRONG / PARTLY | Evidence |
|-------|------------------------|----------|
| (a) Byte 6 flag: 08=active, ff=idle, 00=head | VALID | Found 647×flag=08 (active claims: Bob Wagner, Hugh Willis, etc.), 17,816×flag=ff (idle history like Mark Loretta), 3,217×flag=00 (head records k=0). All three values present with claimed meanings. |
| (b) rel is related PLAYER id, not team/money | VALID | Sampled 15 rel values: all are player IDs with names (1973=Bob Wagner, 1896=Marv Kubek, 2176=Sam Wagner, etc.). Flag=08 records have rel=pid (same player); flag=ff records have rel=0 or different player (example: pid=2276 John Aragon → rel=2176 Sam Wagner confirmed day05+). |
| (c) ev stable for same player-event across days | VALID | Spot-checked pid=1973 Bob Wagner (ev=08 consistent across day01-day07), pid=1701 Bill Ginn (ev=05 identical day01/day02/day10). p24 pointers also identical when ev matches. |
| (d) Date format (era<<8)\|day; era 47 day 206=April 3 | VALID | Dates 206/47, 207/47, 208/47, 209/47, 210/47, 211/47 appear in progression matching April calendar. Day values increase sequentially; era byte (46 vs 47) separates seasons. Format confirmed via byte positions r[21]/r[22]. |
| (e) c23=0x0B and c24=00 constants for real records | WRONG | c23=0b c24=00 appears 34,286 times (92% of 37,316 total), not constant. Found c23=00 with c24=0a, c23=f7 with c24=00, c23=00 c24=de, c23=0a c24=03 in valid records. High prevalence ≠ universal constant. |

**SUMMARY:** 4 of 5 claims VALID. Date format and player ID field confirmed. Flag semantics correct. Stability of event codes verified. Only c23/c24 "constant" claim is wrong—they're dominant (92%) but not universal across real records.
