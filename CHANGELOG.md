# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-02

First release. The method, the data, the live evaluation and a no-key replay of every
published number are complete.

### Added

- **Data.** NHTSA ODI complaints and recalls become a 20,000-item past-case library, a
  400-item evaluation set, a weekly trend table and a mapped recall table, with a PII
  screen, dropped identity and location columns, a derivation record and file checksums.
- **Extraction.** Prompt `e1`, a strict wire schema, and a verbatim quote check that drops
  any clue whose quote is not in the narrative.
- **Model client.** A record/replay client for the OpenAI-compatible gateway, with
  per-model pacing, retry and stop rules, cost accounting and committed recordings.
- **Similar cases.** Pinned CPU embeddings (`BAAI/bge-small-en-v1.5`), a cached library
  index, and precision@5 scoring.
- **Rules.** Hard rules `hr1` (safety wins, unclear goes to a person, no decision state),
  rulebook `rb1`, the triage card, the technician feedback log and the KPI definitions.
- **Trend watch.** Weekly spike detection per make, model, model year and group, with a
  recall backtest that reports the base rate beside the alert share.
- **Pipeline.** `frt triage`, `frt eval` in replay and record mode, a budget guard,
  metrics with confidence intervals, the cost-free baselines, `results/SUMMARY.md` and a
  results manifest.
- **Live evaluation.** Two models locked from the sibling model-selection card, the
  primary on 400 items and the comparison on 200 under the budget cap, with every call
  recorded and replayed.
- **Documentation.** This changelog, `README.md`, `METHOD.md`, `project-facts.yml`, the
  example complaint in `docs/`, and the licence and credit record in `THIRD_PARTY.md`.

### Notes

- Public commands are replay-only: `make all`, `make test` and `make release-check` need
  no key and no network. The one paid run is recorded in `results/runs/live/`.
- The complaint text is public NHTSA data used as a stand-in for a lab's return reports.
  The rulebook and component groups are examples meant to be adapted.
- Every number in the README and `project-facts.yml` is checked against the committed
  results file that proves it by `make facts`.
