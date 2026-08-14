"""Signals + ingest: the raw_items -> signals pipeline, its sources, and the live feed.

Two things in this folder are invisible to import-based tools, so they are written here:

* **`api_feed.py` imports no model.** Its real contract is `v_live_feed`, a database
  VIEW defined in migrations, read through raw keyset-paginated SQL, plus
  `app/schemas/dashboard.py` (which stays in `app/schemas/` — it is the internal
  dashboard's presentation layer, not a domain contract). Nothing in `app/` can break
  or fix a view/column mismatch.
* **News articles are `Signal` rows** with `kind='news'`, their classification in the
  `signals.ai` JSONB under `ai.news`. `app/domains/news/` reads and writes them across
  the domain boundary by design; there is no news-article model anywhere.

`counterparty_models.py` looks unused and is not: `models.py` declares
`counterparty_id` with a STRING FK target `"counterparties.id"`, so the table only
reaches `Base.metadata` because the barrel imports that module. The ORM classes have no
Python consumer (access is raw SQL or via the FK) — that is a product question about the
entity-resolution process, not licence to delete the import.

`app/ingest/` stays outside `app/domains/` by design and imports `source_models` from
here. That is an adapter layer depending on the model it adapts; do not add a re-export
shim to hide the path.
"""
