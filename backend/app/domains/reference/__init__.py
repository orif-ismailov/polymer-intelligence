"""Reference dictionaries: products, grades, synonyms.

Its own domain rather than a possession of any one consumer, because the consumers span
four: signals, news, marketplace and requests all resolve product text through here.

`relevance.py` and `grades.py` have no `from app.` imports at all — they reach
`products`/`product_grades` through bound-parameter `text()` SQL. P8 and P10 each
declined to claim them for exactly that reason; this is the home they promised.
"""
