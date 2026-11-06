# Security policy

Security fixes are made for the latest commit on `main`.

## Reporting

Report vulnerabilities privately through the repository's **Security** tab ("Report a
vulnerability"). Do not open a public issue.

## Scope

statdrift creates one locked uv environment per release under `envs/`, runs the battery in
each with no network access needed, and writes JSON Lines, JSON, CSV and Markdown under
`results/`. `statdrift envs` downloads pinned packages from PyPI (hashes in each `uv.lock`).
`statdrift notes` downloads release notes from pinned GitHub commits and the GitHub API, and
stores them as data; they are never executed. `diff`, `repeat` and the tests make no network
requests.

In scope:

- statdrift reading, writing or deleting files outside the repository;
- code execution triggered by the contents of `battery.json`, a results file or a note;
- local absolute paths or machine details written to committed outputs.

Out of scope:

- vulnerabilities in SciPy, statsmodels and their dependencies (report those upstream);
- numerical disagreements with a library (statdrift reports change, not correctness).
