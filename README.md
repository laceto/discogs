# Discogs

Collect Discogs data (releases, artists, labels, masters) into local JSON files, and explore it
with a Deep Agents chat assistant. Requests are paced to stay inside the Discogs rate limit.

## Installation

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in the values below
```

`.env` values:

| Variable | Needed for | Where to get it |
|---|---|---|
| `DISCOGS_USER_TOKEN` | all API calls (60 requests/min instead of 25) | https://www.discogs.com/settings/developers |
| `OPENAI_API_KEY` | the chat agent only | https://platform.openai.com/api-keys |
| `DISCOGS_AGENT_MODEL` | optional, default `openai:gpt-5` | |
| `DISCOGS_AGENT_BUDGET` | optional, max Discogs requests per agent run, default 100 | |

## Usage

Collect one record and save it under `data/` (collectors return a dict; `storage` writes it):

```python
from discogs.client import get_client
from discogs.collectors.release import collect_release
from discogs.storage import save_json

record = collect_release(get_client(), 687809)   # a RELEASE id, not a master id
save_json("release", 687809, record)              # -> data/release/687809.json
```

Other collectors: `collect_artist_profile`, `collect_artist_releases`, `collect_label`,
`collect_label_releases`, `collect_master_versions`, `collect_search_releases` (all in
`discogs/collectors/`). A master id is not a release id: use the master's `main_release`.

Chat with the agent (it reads `docs/` and `data/`, can fetch from Discogs within a request
budget, and asks before any bulk crawl):

```bash
python scripts/chat.py                       # new conversation
python scripts/chat.py --thread my-session   # resume a conversation
python scripts/chat.py --budget 300          # allow more Discogs requests this run
```

## Development

```bash
pip install -e ".[dev]"
pytest                      # offline: no network, no API keys needed
ruff check . && mypy --strict discogs
```

## Project structure

```
discogs/
├── discogs/
│   ├── client.py        # authenticated client (uses the rate-limited fetcher)
│   ├── ratelimit.py     # request pacing, low-budget pause, 5xx retry
│   ├── storage.py       # save_json / load_json / list_ids
│   ├── collectors/      # release, artist, label, master, search
│   └── agent/           # Deep Agents agent: tools, agent, session
├── scripts/             # chat.py, discogs_release_reader.py
├── data/                # collected JSON (gitignored)
├── docs/                # architecture.md, schemas.md
├── tests/
└── board/               # planning docs
```

See `docs/architecture.md` for how the pieces fit and `docs/schemas.md` for the stored shapes.

## License

MIT
