<!-- markdownlint-disable MD033 -->
[![CI](https://github.com/ryancswallace/patiencepilot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/ci.yml)
[![Documentation](https://github.com/ryancswallace/patiencepilot/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/docs.yml)
[![Docker](https://github.com/ryancswallace/patiencepilot/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/docker.yml)
[![CodeQL](https://github.com/ryancswallace/patiencepilot/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://github.com/ryancswallace/patiencepilot/actions/workflows/scorecard.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/scorecard.yml)
[![Workflow lint](https://github.com/ryancswallace/patiencepilot/actions/workflows/workflow-lint.yml/badge.svg?branch=main)](https://github.com/ryancswallace/patiencepilot/actions/workflows/workflow-lint.yml)
[![Python 3.11-3.14](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://github.com/ryancswallace/patiencepilot/blob/main/pyproject.toml)
[![Typed with basedpyright](https://img.shields.io/badge/types-basedpyright-2f6fdd)](https://github.com/DetachHead/basedpyright)
[![Linted with Ruff](https://img.shields.io/badge/lint-Ruff-46a2f1)](https://docs.astral.sh/ruff/)
[![Coverage gate: 95%](https://img.shields.io/badge/coverage%20gate-%E2%89%A595%25-2e7d32)](https://github.com/ryancswallace/patiencepilot/blob/main/pyproject.toml)
[![SBOM: CycloneDX 1.6](https://img.shields.io/badge/SBOM-CycloneDX%201.6-6f42c1)](https://cyclonedx.org/)

<!-- markdownlint-disable MD033 -->
<p align="center">
  <strong>
    A Solitaire solver in Python.
  </strong>
</p>

<br>

<p align="center">
  <a href="https://ryancswallace.github.io/patiencepilot/">
    <img
      alt="Open the patiencepilot documentation"
      src="https://img.shields.io/badge/Open%20the%20docs-patiencepilot%20documentation-0f766e?style=for-the-badge&logo=githubpages&logoColor=white"
    >
  </a>
</p>

<br>
<!-- markdownlint-enable MD033 -->

## Install

Install the released package with uv:

```bash
uv add patiencepilot
```

or with pip:

```bash
python -m pip install patiencepilot
```

For local development from this repository:

```bash
make ready
```

## Documentation

The documentation source lives under [`docs/`](docs/). The top-level Markdown
files are short project entry points; detailed guides, explanations, references,
and runbooks live in the MkDocs documentation.

The MkDocs site builds in strict mode and generates API reference pages from the
package docstrings.

## Project Links

* [Contributing](CONTRIBUTING.md)
* [Changelog](CHANGELOG.md)
* [Security policy](SECURITY.md)
* [Release policy](RELEASING.md)
* [Code of conduct](CODE_OF_CONDUCT.md)
* [Citation metadata](CITATION.cff)

## License

patiencepilot is distributed under the [MIT License](LICENSE).
