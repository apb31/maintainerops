# MaintainerOps

MaintainerOps is an open-source command-line tool that turns public GitHub repository activity into a compact maintenance report.

It helps maintainers quickly see:

- open issues and pull requests
- stale issues and stale pull requests
- repository stars and forks
- latest release and release age
- JSON or CSV output for scripts, spreadsheets, and automation

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/apb31/maintainerops.git
cd maintainerops
python -m pip install -e .
```

## Usage

```bash
maintainerops psf/requests
maintainerops openai/openai-python --json
maintainerops owner/repo --csv
maintainerops owner/repo --stale-days 45
```

For higher GitHub API rate limits, set `GITHUB_TOKEN` in your environment. A token is not required for public repositories.

## Example output

```text
Repository: psf/requests
Stars: 50000+ | Forks: 9000+
Open issues: 100 (25 stale)
Open PRs: 40 (12 stale)
Latest release: vX.Y.Z
```

Values above are illustrative; MaintainerOps always reads current GitHub API data.

## Why this project exists

Open-source maintainers often spend time collecting context before deciding what to review, close, prioritize, or release. MaintainerOps provides a reproducible first-pass report that can be used manually or as an input to maintenance automation.

## Roadmap

- pagination and contributor activity summaries
- label and milestone health checks
- CI failure summaries
- issue clustering
- release-note assistance
- optional AI-assisted triage with explicit human review

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
