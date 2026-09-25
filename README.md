# Discogs

> Short one-line description.

## Installation

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Usage

```python
import discogs

# ...
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Project structure

```
discogs/
├── discogs/            # main package
├── scripts/            # utility scripts
├── data/                # data files (gitignored by default)
├── tests/               # test suite
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT
