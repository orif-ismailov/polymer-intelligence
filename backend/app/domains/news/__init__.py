"""News + reports domain.

**There is no news-article model here, and there is no `news_articles` table.** A news
article IS a `Signal` row with `kind='news'`; the whole rich classification — headline,
category, importance, market_impact, summary — lives in that row's `signals.ai` JSONB
under `ai.news`. `news_service`'s docstring records the decision (Option A: no schema
migration). So `models.py` in this folder holds only `Report`, and anyone looking for
"the news model" wants `app/models/signals.py` plus the `ai.news` block.

That also means this domain reads and writes `Signal` across a domain boundary, by
design — do not give news a model of its own to make the folder look complete.
"""
