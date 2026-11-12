# Judgment log

## 1. Blank names

- **Problem:** The spec says farm names can't be empty but says nothing about plot names.
- **My answer:** Farm and plot names can't be empty or whitespace-only.
- **Reason:** Blank names are meaningless, and one rule for both names keeps things consistent.

## 2. What "today" means

- **Problem:** The spec doesn't define "today" for the rule that `planting_date` can't be in the future.
- **My answer:** "Today" is the UTC date.
- **Reason:** UTC gives the same date on every server.

## 3. Unknown request fields

- **Problem:** The spec doesn't say what to do with fields the API doesn't recognize.
- **My answer:** Reject them with 422.
- **Reason:** A typo in a PATCH body would otherwise return 200 and silently change nothing.

## 4. Moving a plot to another farm

- **Problem:** The spec doesn't say whether PATCH can change a plot's `farm_id`.
- **My answer:** Yes, if the new farm exists and the plot name is unique there.
- **Reason:** The spec says PATCH updates any field provided.

## 5. List order

- **Problem:** The spec doesn't define the order of list responses.
- **My answer:** Sort by name, then id.
- **Reason:** It gives a stable, predictable order.

## 6. Plot-name case sensitivity

- **Problem:** The spec doesn't say whether plot-name uniqueness is case-sensitive.
- **My answer:** Case-sensitive.
- **Reason:** It matches the database's UNIQUE index, so the app check and the database always agree, even in a race.

## 7. Request body that isn't valid JSON

- **Problem:** Malformed JSON returned 422, but invalid UTF-8 returned 400 (FastAPI's default).
- **My answer:** Both return `422 VALIDATION` with `body: could not be read as JSON`.
- **Reason:** Both are bad request bodies, and the spec maps validation errors to 422. A test pins FastAPI's message text, so an upgrade that changes it fails loudly.

## 8. Where a new plot's id comes from

- **Problem:** `plots` keeps `id` as its primary key, so every new plot needs one. The client could send it, or the server could generate it.
- **My answer:** The server generates the id and returns it in the POST response.
- **Reason:** Routes use `/v1/plots/{id}`, and the original design already generated ids on the server.

## 9. Farm area endpoint

- **Problem:** The spec doesn't define `GET /v1/farms/{id}/area`: its response body, or what a farm with no plots returns.
- **My answer:** It returns `{"area_m2": <sum of the farm's plot areas>}`. A farm with no plots returns `200` with `area_m2` of `0`. An unknown farm returns `404`.
- **Reason:** The field reuses the plot field name, so the unit is clear and nothing else is exposed. Zero is the true sum of no plots, and an existing farm with no plots is a valid state, like an empty list.
