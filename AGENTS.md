# AGENTS.md: rules for every agent working in this repository

This repo is built autonomously by firstmate crewmates from `PLAN.md` (the frozen method) and `plan/TASKS.md` (the task briefs). Your brief is your task's section in `plan/TASKS.md`.

1. **Stay in your lane.** Edit only the files your brief lists under "Owns". The smallest additive change to shared code is allowed only if explained in `reports/lanes/<ID>.md`.
2. **Never edit `PLAN.md` §1–§11.** If the method seems wrong, write `reports/STOP.md` and stop.
3. **No paid model calls and no network in tests**, except R7 (the live run), R1's data download and R3's one-time embedding-model download. `make test` runs with sockets blocked.
4. **Secrets:** keys only in the env file named by `FRT_ENV_FILE` (or a gitignored `.env`), referenced as `env:NAME`. Never print environment variables. Never read the env file with shell tools. Never put a key on a command line, in a log, trace, recording, test or commit. Run `make scan-secrets` before committing.
5. **Names:** `make scan-forbidden` must pass (hashed list in `config/forbidden.sha256`). This is an independent project: never name an employer or a private person, in files or commit messages.
6. **Numbers** shown in the README, on the page or in `project-facts.yml` come only from committed files in `results/`.
7. **Quality bar:** Python 3.12, `uv`, Ruff, strict mypy on `src/` (documented exceptions only), pytest. Small, readable modules; match the surrounding style.
8. **Finish** with a lane report `reports/lanes/<ID>.md`: what was built, how it was tested, deviations, open issues. Then leave a clean, ready branch.
9. **Never push, never add a remote, never publish.** The captain publishes.
