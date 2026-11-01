# Third-party data and licences

Everything this project commits that was not written here, with its source, licence and
the exact wording that supports it. The binding machine-readable copy of this licence
record is `data/nhtsa-spec.toml`, copied byte for byte from data scout X0.

## NHTSA ODI vehicle owner complaints

| | |
|---|---|
| Publisher | U.S. Department of Transportation, National Highway Traffic Safety Administration (NHTSA), Office of Defects Investigation |
| Dataset | ODI complaints, flat files for complaints received 2020-2024 and 2025-2026 |
| Snapshot date | 2026-10-31 |
| Snapshot files | `COMPLAINTS_RECEIVED_2020-2024.zip`, `COMPLAINTS_RECEIVED_2025-2026.zip` |
| Source URLs | <https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2020-2024.zip><br><https://static.nhtsa.gov/odi/ffdd/cmpl/COMPLAINTS_RECEIVED_2025-2026.zip> |
| Field layout | <https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt> |
| Catalogue record | <https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-complaints> (identifier `DOT-81`) |
| Licence | U.S. Government work, public domain — [us-pd label](http://www.usa.gov/publicdomain/label/1.0/) |
| SHA-256 (2020-2024) | `c11743646e7d6dd2466ce11667dcee9450ef9763bc7a0c9175d1c891b1fa33bb` |
| SHA-256 (2025-2026) | `dd92183e9b12bbf3e474e440c0951dd15810f0e1f1ee01dfcf41b064d21fb423` |

## NHTSA ODI vehicle recalls

| | |
|---|---|
| Publisher | U.S. Department of Transportation, National Highway Traffic Safety Administration (NHTSA), Office of Defects Investigation |
| Dataset | Part 573 safety recall flat file, post-2010 |
| Snapshot date | 2026-10-31 |
| Snapshot file | `FLAT_RCL_POST_2010.zip` |
| Source URL | <https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip> |
| Field layout | <https://static.nhtsa.gov/odi/ffdd/rcl/RCL.txt> |
| Catalogue record | <https://catalog.data.gov/dataset/nhtsas-office-of-defects-investigation-odi-recalls> (identifier `DOT-83`) |
| Licence | U.S. Government work, public domain — [us-pd label](http://www.usa.gov/publicdomain/label/1.0/) |
| SHA-256 | `5d8cc101ff4c191d87234bbac807c73b92348a3a48fca9a2281436d704c99c56` |

## Licence evidence, as retrieved on 2026-10-31

NHTSA's site policy, section *Ownership*
(<https://www.nhtsa.gov/about-nhtsa/privacy-policy>):

> "Information presented on this web site is considered public information and may be
> distributed or copied."

The data.gov catalogue metadata for both datasets names
`license = http://www.usa.gov/publicdomain/label/1.0/` and `accessLevel = public`; the
older catalogue page states it in words:

> "Public: This dataset is intended for public access and use. License: us-pd"

The public-domain label page defines the scope and the caveat
(<https://www.usa.gov/government-copyright>):

> "Government work is something created by a U.S. government officer or employee as part
> of their official duties."

> "On federal websites, other people may have rights to the work itself or how people use
> it. This includes publicity or privacy rights under state law."

**Conclusion.** Both datasets are U.S. Government works in the public domain, and derived
extracts may be redistributed. The privacy sentence is the reason for the hard rule in
`PLAN.md` section 5, not a redistribution restriction: the complaints contain personal
data contributed by the public, so identity and location columns are dropped and a
narrative that matches the PII screen is discarded, never committed.

## What this project commits from them

- `data/library.jsonl.gz` — 20,000 past cases from complaints received 2020-2024.
- `data/eval.jsonl` — 400 evaluation complaints received 2025-2026, `frt` half.
- `data/trend/weekly.csv.gz` — weekly counts per make, model, model year and group.
- `data/trend/recalls.csv` — recall rows whose component maps to a group.
- `data/STATS.md` and `data/CHECKSUMS.txt` — the derivation record and file hashes.

The raw downloads are never committed (`data/raw/` is gitignored). The copied normative
files `data/nhtsa-spec.toml` and `data/groups.toml` are part of this licence record.

Identity and location columns (`CITY`, `STATE`, `VIN`, `STATE_OF_INCIDENT`,
`VEHICLE_OPERATOR`, `DEALER_NAME`, `DEALER_TEL`, `DEALER_CITY`, `DEALER_STATE`,
`DEALER_ZIP`) are dropped from every derived file. The committed data is a set of public
complaints, not return reports, and is used as a stand-in for a lab's own complaint text.
