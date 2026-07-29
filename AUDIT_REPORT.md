# Kerala Clean Cooking Tool — Full Code & Data Audit

**Scope:** `user_data.db` table architecture and storage strategy, the database code paths, CSS, HTML templates, and internationalization (i18n).
**App:** Flask + SQLite web tool (residential & commercial cooking-energy analysis, English/Malayalam).
**Date:** 2026-07-28
**Method:** 6 specialist review passes over the actual source and both live databases, with an **adversarial verification pass** re-checking every database claim by replaying statements on a throwaway copy of `user_data.db` and querying the live schema. Database findings are marked *confirmed / partly / rejected* accordingly.

> **How to read this document.** Start with the **Executive Summary** and the **Master Issue Register** (all 72 findings, severity-ranked). Then dive into the five detailed parts. The **Remediation Roadmap** sequences the fixes. Appendix A is a table-by-table inventory of `user_data.db`; Appendix B documents the verification method.

---

## 1. Executive Summary

### Your core question: *"Is `user_data.db` the best/optimal way to store this data?"*

**No — not as it stands — but the fix is the schema and the write layer, not the database engine.** Two of the three big architectural choices are actually **right and should be kept**:

1. **Splitting reference data (`cooking_webapp.db`, read-only) from user data (`user_data.db`, read-write) is a good separation.** Keep it.
2. **SQLite is the correct engine for this workload** — a single-writer Flask app, ~12 households, a 220 KB database. Postgres would add operational cost with no benefit at this scale. Revisit only if you add concurrent writers or need server-side analytical queries at volume.

The design fails on the **details**, and several of them are serious:

- 🔴 **One whole table is silently broken.** `user_analysis_history` is written with columns (`user_id, activity_type, details`) that **do not exist** in the on-disk table, so every write throws and is swallowed — the activity log has **0 rows and always will**. Root cause: `CREATE TABLE IF NOT EXISTS` is being used as a migration strategy, so the code's expected schema and the on-disk schema have silently drifted apart.
- 🟠 **The database is simultaneously over-designed and under-normalized.** A clean normalized schema (`residential_fuel_selections`, `residential_dish_selections`, `commercial_fuel_selections`, `alternative_recommendations`) was built, indexed, and given writer functions — but those writers **are never called** (all tables are 0 rows). The real data is hidden as **opaque nested JSON blobs** in `cooking_analysis.fuel_breakdown` / `commercial_analysis.fuel_breakdown`, and there is **zero `json_extract` usage** anywhere — so for a *survey/analytics* tool, none of the aggregate questions it exists to answer ("how many households use LPG", "average payback by district") are answerable in SQL today.
- 🟠 **Structural relational hygiene is missing:** three data tables have **no primary key** (causing duplicate rows and making `INSERT OR REPLACE` a silent no-op), money is stored as **raw IEEE-754 floats**, and the only indexes in the database sit on **empty tables** while the columns actually queried are unindexed.
- 🟠 **Two overlapping data-access layers** (`helper.py` and `database/db_helper.py`) manage the same database with **different, conflicting connection policies** — and this is exactly why the schema drift above goes unnoticed: there is no single source of truth.

Beyond the database, the audit found a **critical CSS/build issue** (the "minified" CSS that ships is not minified and has silently diverged from its source), multiple **WCAG contrast failures on primary UI**, a **functional form bug in the feedback page**, unbalanced markup in two templates, and a set of i18n gaps (no Malayalam webfont, a second translation layer in the PDF generator) — though the gettext **catalog itself is in excellent shape** (589 messages, 100% translated to Malayalam, 0 fuzzy, 0 placeholder-mismatch risk).

### Severity dashboard

| 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ⚪ Info | **Total** |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | 13 | 24 | 29 | 5 | **72** |

**The five things to fix first:**

1. 🔴 Migrate `user_analysis_history` (or fix `log_user_history`) and **stop using `CREATE TABLE IF NOT EXISTS` for schema evolution** — adopt real migrations.
2. 🟠 **Decide normalization once:** wire up the dead `save_fuel_selections`/`save_dish_selections` writers and make the normalized tables the source of truth (recommended), *or* delete them and query the JSON via SQLite JSON1. Do not keep both.
3. 🟠 Add **primary keys / uniqueness** to `cooking_analysis`, `commercial_analysis`, `recommendations`; index the FK columns that are actually queried.
4. 🟠 Fix the **CSS build**: make `style.min.css` a generated artifact from one source of truth, and repair the **contrast failures** on the hero stats, primary CTA, and Back button.
5. 🟠 Fix the **feedback-form "No" path** (required fields trapped in a visually-collapsed section block submission) and the **unbalanced `<div>`s** in `analysis.html` / `commercial_analysis.html`.

---

## 2. Master Issue Register

All 72 findings, ranked by severity then area. "Verified" reflects the adversarial pass (database items only; front-end items were single-pass reviewed).

| # | Sev | Area | Finding | Location | Verified |
|---|---|---|---|---|---|
| 1 | 🔴 critical | DB / Architecture | CREATE TABLE IF NOT EXISTS drift silently breaks user_analysis_history (0 rows forever) | `helper.py:488-496 & :742; user_analysis_history on-disk DDL` | ✔ confirmed |
| 2 | 🟠 high | CSS | Served style.min.css is unminified AND diverged from style.css (two brand tokens differ) | `templates/base.html:24; static/css/style.min.css:11-12 vs static/css/style.css:11-12` | — |
| 3 | 🟠 high | CSS | Hero stat numbers illegible: accent-yellow #F2C851 on white = 1.60:1 | `static/css/style.min.css:1118 (.stat-value); templates/index.html:32,37,42` | — |
| 4 | 🟠 high | CSS | Primary homepage CTA fails contrast: white on light-green #4CAF50 = 2.78:1 | `static/css/style.min.css:1047 (.cta-primary); templates/index.html:24` | — |
| 5 | 🟠 high | CSS | Back button label vanishes on hover: white on accent-yellow = 1.60:1 | `static/css/style.min.css:480 (.btn-nav-back:hover)` | — |
| 6 | 🟠 high | DB / Architecture | Money stored as raw IEEE-754 floats in DECIMAL columns | `cooking_analysis.current_monthly_cost / monthly_energy_kwh (DECIMAL(8,2))` | ✔ confirmed |
| 7 | 🟠 high | DB / Architecture | No primary keys on cooking_analysis, recommendations, commercial_analysis | `cooking_analysis / recommendations / commercial_analysis (PRAGMA table_info shows PK=[])` | ✔ confirmed |
| 8 | 🟠 high | DB / Architecture | Indexes sit on 0-row tables; the actual FK query columns are unindexed | `cooking_analysis.household_id, recommendations.household_id, commercial_analysis.institution_id` | partly |
| 9 | 🟠 high | DB / Code & Integrity | log_user_history() inserts into non-existent columns — 100% silent failure | `helper.py:742` | ✔ confirmed |
| 10 | 🟠 high | DB / Code & Integrity | Commercial recommendations silently dropped (household-keyed guard rejects institution_id) | `app.py:1315` | ✔ confirmed |
| 11 | 🟠 high | DB / Code & Integrity | INSERT OR REPLACE on keyless commercial_analysis + duplicate save paths append duplicates | `commercial_cooking.py:1288` | ✔ confirmed |
| 12 | 🟠 high | DB / Code & Integrity | save_user_feedback swallows IntegrityError with no rollback, losing feedback silently | `helper.py:730` | partly |
| 13 | 🟠 high | HTML (commercial) | Required fields in visually-collapsed section block the "No" submission path | `templates/feedback.html:80-81,225-243,314` | — |
| 14 | 🟠 high | HTML (residential) | Dynamic _(variable) fuel/category strings are not extractable by Babel | `templates/analysis.html:143,293,335,385; energy_calculation.html:108; kitchen_profile.html:58` | — |
| 15 | 🟡 medium | CSS | Core brand green #228B22 only meets AA for large text; used for form labels, links, chart titles | `static/css/style.min.css:138,123,547,833 (h1-h6, a, .form-label, .chart-title)` | — |
| 16 | 🟡 medium | CSS | One-pixel breakpoint gap disables mobile touch-target and layout rules at fractional widths | `static/css/style.min.css:1672,724,1445,1468,1412,1543 (max-width:767px) vs 342 (767.98px) and 768px min-width blocks` | — |
| 17 | 🟡 medium | CSS | No print styles for the PDF/report pages | `static/css/style.min.css (no @media print anywhere)` | — |
| 18 | 🟡 medium | CSS | Language switcher label fails contrast: 3.18:1 | `static/css/style.min.css:288 (.lang-btn)` | — |
| 19 | 🟡 medium | DB / Architecture | Designed normalized *_selections tables are dead; real data is an opaque JSON blob | `cooking_analysis.fuel_breakdown (TEXT) vs residential_fuel_selections/residential_dish_selections (0 rows)` | ✔ confirmed |
| 20 | 🟡 medium | DB / Architecture | Redundant feedback columns with a mis-mapped write | `helper.py:706-723; user_feedback png_scheme_interested/support_png etc.` | ✔ confirmed |
| 21 | 🟡 medium | DB / Architecture | Polymorphic entity_id/entity_type instead of real foreign keys, with inconsistent vocabulary | `alternative_recommendations(entity_id,entity_type) & user_feedback(entity_id,entity_type); helper.py:1042` | ✔ confirmed |
| 22 | 🟡 medium | DB / Code & Integrity | Foreign keys reference non-existent and cross-database tables | `helper.py:494` | ✔ confirmed |
| 23 | 🟡 medium | DB / Code & Integrity | households.current_fuels/calculation_method always empty, kitchen_scenario always NULL | `app.py:350` | ✔ confirmed |
| 24 | 🟡 medium | DB / Code & Integrity | Reference DB opened read-write by db_helper despite read-only contract; two divergent DB layers | `database/db_helper.py:76` | partly |
| 25 | 🟡 medium | HTML (commercial) | ~470 lines of chart JS duplicate main.js | `templates/commercial_analysis.html:814-1305` | — |
| 26 | 🟡 medium | HTML (commercial) | Unclosed <div class="container"> — one unbalanced div in content block | `templates/commercial_analysis.html:35,773` | — |
| 27 | 🟡 medium | HTML (commercial) | Action Center card sits in .row with no column wrapper | `templates/commercial_analysis.html:702` | — |
| 28 | 🟡 medium | HTML (commercial) | Chart guard requires health data though no health/radar canvas exists | `templates/commercial_analysis.html:866` | — |
| 29 | 🟡 medium | HTML (commercial) | Dynamic values passed to _() cannot be extracted for translation | `templates/commercial_analysis.html:304,462,505,559` | — |
| 30 | 🟡 medium | HTML (residential) | analysis.html Strategic Recommendations card is never closed | `templates/analysis.html:261 (card-body closes at 433; no card </div>)` | — |
| 31 | 🟡 medium | HTML (residential) | kitchen_profile.html .container div is never closed | `templates/kitchen_profile.html:12` | — |
| 32 | 🟡 medium | HTML (residential) | error.html has no .container wrapper (row bleeds to edges) | `templates/error.html:6` | — |
| 33 | 🟡 medium | HTML (residential) | Energy page inputs are not inside a <form>; required attrs and CSRF are non-functional semantically | `templates/energy_calculation.html:12,252` | — |
| 34 | 🟡 medium | HTML (residential) | Step pages have no <h1> and jump/invert heading levels | `templates/household_profile.html:13; energy_calculation.html:15,85,124; kitchen_profile.html:23; analysis.html:26` | — |
| 35 | 🟡 medium | HTML (residential) | Calculation-method radios have no associated label | `templates/energy_calculation.html:39,60` | — |
| 36 | 🟡 medium | i18n | No Malayalam webfont loaded; only Poppins (Latin) is fetched | `templates/base.html:21 / static/css/style.css:91,187` | — |
| 37 | 🟡 medium | i18n | ~7 flash() error strings hardcoded in English and never rendered | `app.py:1014,1031,1061,1115,1164,1179,1287` | — |
| 38 | 🟡 medium | i18n | pdf_generator.py is a second translation layer that bypasses gettext | `pdf_generator.py` | — |
| 39 | 🔵 low | CSS | 49 !important declarations, largely re-implementing Bootstrap utilities already loaded | `static/css/style.min.css:200-220,175,1649,181 (utility classes)` | — |
| 40 | 🔵 low | CSS | Duplicated show/hide rules in stylesheet and inline base.html <style> | `static/css/style.min.css:337-345; templates/base.html:34-53` | — |
| 41 | 🔵 low | CSS | overflow-x:hidden on html and body masks a real layout-overflow bug | `static/css/style.min.css:86,96` | — |
| 42 | 🔵 low | CSS | No prefers-reduced-motion guard on animations and hover transforms | `static/css/style.min.css:1612-1635,361-366 (keyframes, hover transforms)` | — |
| 43 | 🔵 low | CSS | Faint focus ring on form inputs; .btn-sm below 44px touch target | `static/css/style.min.css:544,595 (outline:none), 496 (.btn-sm)` | — |
| 44 | 🔵 low | CSS | Hardcoded hex values bypass the token system; no RTL logical properties | `static/css/style.min.css (repeated #e9ecef, #f8f9fa, #5da55d; border-left/margin-left/translateX throughout)` | — |
| 45 | 🔵 low | DB / Architecture | Inconsistent DEFAULT literal quoting and dangling FK targets | `households.country_code DEFAULT '+91' vs commercial_institutions.country_code DEFAULT "+91"; FKs to households_new / commercial_cooking_analysis` | ✔ confirmed |
| 46 | 🔵 low | DB / Architecture | Two overlapping data-access layers with duplicated cache DDL | `database/db_helper.py (DatabaseHelper, l.94-103) vs helper.py get_user_connection() (l.223) + analysis_cache DDL (l.538)` | ✔ confirmed |
| 47 | 🔵 low | DB / Code & Integrity | f-string SQL identifiers (not currently exploitable) | `helper.py:281` | ✔ confirmed |
| 48 | 🔵 low | DB / Code & Integrity | Read helpers lack try/finally — connection leak on JSON parse error outside request context | `helper.py:805` | ✔ confirmed |
| 49 | 🔵 low | HTML (commercial) | Institution types and dish names rendered untranslated | `templates/commercial_analysis.html:43,55,94,241` | — |
| 50 | 🔵 low | HTML (commercial) | console.debug leaks user PII to the browser console | `templates/feedback.html:9-14` | — |
| 51 | 🔵 low | HTML (commercial) | Radio/checkbox groups lack fieldset/legend semantics | `templates/commercial_energy_calculation.html:101` | — |
| 52 | 🔵 low | HTML (commercial) | Method cards are mouse-only (not keyboard operable) | `templates/commercial_energy_calculation.html:45` | — |
| 53 | 🔵 low | HTML (commercial) | Phone pattern forces 10 digits regardless of selected country code | `templates/commercial_selection.html:132` | — |
| 54 | 🔵 low | HTML (commercial) | current_fuel_mix submitted twice in dish mode | `templates/commercial_energy_calculation.html:107,658` | — |
| 55 | 🔵 low | HTML (commercial) | Large commented-out dead markup left in template | `templates/commercial_analysis.html:639-700` | — |
| 56 | 🔵 low | HTML (residential) | Method cards are mouse-only (not keyboard operable) | `templates/energy_calculation.html:35,56` | — |
| 57 | 🔵 low | HTML (residential) | country_code select is unlabeled | `templates/household_profile.html:46` | — |
| 58 | 🔵 low | HTML (residential) | Leftover console.debug ships full fuel breakdown to prod | `templates/analysis.html:536` | — |
| 59 | 🔵 low | HTML (residential) | Dead JS references non-existent elements | `templates/analysis.html:558; kitchen_profile.html:149,203` | — |
| 60 | 🔵 low | HTML (residential) | Vasudha Foundation alt text not wrapped for i18n | `templates/base.html:69,155` | — |
| 61 | 🔵 low | HTML (residential) | Fragile JSON.parse('{{ x/tojson/safe }}') pattern | `templates/energy_calculation.html:607,608,626; analysis.html:538` | — |
| 62 | 🔵 low | HTML (residential) | Large repeated markup blocks should be Jinja macros/loops | `templates/energy_calculation.html:121-217; analysis.html:290-425; base.html:64-81/154-157` | — |
| 63 | 🔵 low | HTML (residential) | Duplicate Bootstrap Icons loading and no SRI on CDN assets | `templates/base.html:16,28-32,13,21,170` | — |
| 64 | 🔵 low | i18n | Two logo alt attributes hardcoded in English | `templates/base.html:69,155` | — |
| 65 | 🔵 low | i18n | Meta description hardcoded in English, never localized | `templates/base.html:7` | — |
| 66 | 🔵 low | i18n | Translation compilation is manual; no JS extractor; drift risk | `compile_translations.bat / babel.cfg` | — |
| 67 | 🔵 low | i18n | Language switch requires JavaScript; state-changing GET | `templates/base.html:105-108,176` | — |
| 68 | ⚪ info | DB / Code & Integrity | Normalized selection tables and their writer functions are never called (dead schema) | `helper.py:927` | ✔ confirmed |
| 69 | ⚪ info | HTML (commercial) | External CDN dependencies break offline use and complicate CSP | `templates/base.html:13` | — |
| 70 | ⚪ info | HTML (residential) | No-op half-step spacing classes and broken flex spacer | `templates/household_profile.html:10-11; analysis.html:24; analysis_selection.html:29,52` | — |
| 71 | ⚪ info | i18n | Redundant double Babel initialization | `app.py:49,214` | — |
| 72 | ⚪ info | i18n | Catalog uses no parameterized gettext (0 placeholders) — no crash risk, but a note | `translations/*/LC_MESSAGES/messages.po` | — |

---

## 3. Database — Architecture Assessment

*Is `user_data.db` the optimal way to store this data? Full analysis, with example target DDL.*

## Verdict

**No — `user_data.db` is not the optimal design as it stands, but the problem is the *schema and write layer*, not the choice of SQLite or the two-file split.** Two of the three architectural decisions are actually sound: (1) splitting read-only reference data (`cooking_webapp.db`) from read-write user data (`user_data.db`) is a good separation and should be kept; (2) SQLite is appropriate for this workload (single-writer Flask app, ~12 households, ~220 KB DB — Postgres would add operational cost with no benefit at this scale). The design fails on the *details*: schema drift that silently breaks a whole table, missing primary keys causing duplicate rows, missing indexes on the exact columns that are queried (while the only indexes present sit on 0-row tables), money stored as raw binary floats in `DECIMAL` columns, a fully-designed normalized schema that is dead code because the app writes opaque JSON blobs instead, and redundant/mis-populated columns. These are fixable with a migration; they do not require changing the engine.

The single most important structural fact: **the normalized tables that would make this a proper relational schema exist but are never written to.** `residential_fuel_selections`, `residential_dish_selections`, `commercial_fuel_selections`, `commercial_dish_selections`, and `alternative_recommendations` are all 0 rows, and `save_fuel_selections`/`save_dish_selections` (`helper.py:927`/`966`) are defined but have **no callers anywhere in the codebase** (grep confirms only the `def` lines). The identical data is serialized as a JSON blob into `cooking_analysis.fuel_breakdown` / `commercial_analysis.fuel_breakdown` (TEXT). So the database is simultaneously over-designed (dead normalized tables + indexes) and under-normalized (real data hidden in blobs).

---

### 1. Schema drift is silently corrupting one table completely (CRITICAL)

`init_user_database()` issues `CREATE TABLE IF NOT EXISTS user_analysis_history (... user_id, activity_type, details ...)` (`helper.py:488–496`). But the table already exists on disk with a *completely different* schema:

```sql
-- ACTUAL on-disk DDL (SELECT sql FROM sqlite_master)
CREATE TABLE user_analysis_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id TEXT NOT NULL,
    analysis_snapshot TEXT, calculation_parameters TEXT,
    system_version VARCHAR(20), analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(50), user_agent TEXT, session_duration_seconds INTEGER,
    pdf_downloaded BOOLEAN DEFAULT 0,
    FOREIGN KEY (household_id) REFERENCES households_new(household_id)  -- table does not exist
)
```

Because `CREATE TABLE IF NOT EXISTS` is a no-op when the table exists, the code's expected columns are never created. Every `log_user_history()` call (`helper.py:742`) runs `INSERT INTO user_analysis_history (user_id, activity_type, details)` against columns that don't exist, raises `OperationalError`, and is swallowed by `except Exception: print(...)` (`helper.py:746–747`). _Verification note: reproduced directly — the insert raises `OperationalError: table user_analysis_history has no column named user_id`._ Result: **0 rows, forever**, and the failure is invisible. This is the archetypal danger of `CREATE TABLE IF NOT EXISTS` as a migration strategy — it cannot evolve an existing table, so code and disk drift apart with no error surfaced. The FK also points at `households_new`, which does not exist (confirmed absent from `sqlite_master`). Fix requires an explicit migration (rename/rebuild), not another `IF NOT EXISTS`.

### 2. Money stored as raw floats in `DECIMAL(x,y)` columns (HIGH)

SQLite has no fixed-point type; `DECIMAL(8,2)` only confers **NUMERIC affinity** and does *not* round or constrain scale (verified: inserting `596.6195738533768` into a `DECIMAL(8,2)` column stores it verbatim as `real`). Observed reality in `cooking_analysis`:

| column | declared | stored typeof() | example value |
|---|---|---|---|
| `current_monthly_cost` | `DECIMAL(8,2)` | `real` in some rows, `integer` in others | `596.6195738533768`, `922` |
| `monthly_energy_kwh` | `DECIMAL(8,2)` | `real` | `70.56935384615385` |

Currency is being persisted with 13 fractional digits of IEEE-754 float, and the *same column* holds a mix of `real` and `integer` storage classes across rows. Consequences: sums are not deterministic/auditable, rounding is entirely at the mercy of the Python caller, and any `= <literal>` filter on a stored float is fragile. _Verification note: the original claim that "`= 922.00` can miss" was imprecise — SQLite compares numerically, so `922 = 922.0` evaluates true and the int/real storage-class mix is by itself harmless for equality. The genuine equality hazard is float representation error (`(0.1+0.2) = 0.3` returns false), which is why storing money as floats and later filtering by an exact value is unsafe._ For a tool that reports rupee costs and payback periods, money should be stored as **integer paise** (`monthly_cost_paise INTEGER`) or rounded to 2 dp in the app before insert. This affects every money/emissions/energy column across `cooking_analysis`, `commercial_analysis`, `recommendations`, and the unused `*_selections` tables.

### 3. No primary keys → duplicate rows, no UPDATE-by-id, no clean FK target (HIGH)

`cooking_analysis`, `recommendations`, and `commercial_analysis` have **no primary key** (verified via `PRAGMA table_info`, PK list empty for all three). Concrete consequences already visible in the live data:

- `cooking_analysis` has a **duplicate**: household `a53aefb5-…` has 2 rows. With no PK/unique constraint, re-running an analysis *appends* rather than updates — there is no `UPDATE ... WHERE id = ?` path possible. (`get_cooking_analysis()` uses `fetchone()`, so it silently returns only the first of the two rows.)
- `recommendations` (33 rows) has 9 rows for household `a53aefb5-…`, 6 each for `705cbaa6-…` and `3edcbe9f-…`. Because there is no `rank`, `run_id`, or `created_at`, you cannot tell which recommendations belong to which analysis run, nor which is the current set. `get_recommendations()` (`helper.py:825`/`830`) returns *all* runs mixed together.
- These tables cannot be the target of a foreign key from any future child table, because FK targets must be a PK/unique column.

Each of these needs a surrogate/natural PK and, where "one current record per entity" is intended, a `UNIQUE(household_id)` or an explicit `analysis_id` run key.

### 4. Indexes are on the wrong tables (HIGH, cheap fix)

Every explicit index in the DB sits on a **0-row table** (`residential_dish_selections`, `residential_fuel_selections`, `commercial_fuel_selections`, `alternative_recommendations`) or on `user_feedback` (2 rows). Meanwhile the tables that actually hold data and are queried by FK have **no index on the queried column** (`PRAGMA index_list` empty for all three):

| Query (helper.py) | Column filtered | Index? |
|---|---|---|
| `get_cooking_analysis()` `WHERE household_id=?` (l.810) | `cooking_analysis.household_id` | none → full scan |
| `get_recommendations()` `WHERE household_id=?` (l.830) | `recommendations.household_id` | none → full scan |
| `get_commercial_analysis()` `WHERE institution_id=?` (l.1106) | `commercial_analysis.institution_id` | none → full scan |

_Verification note: the original table cited `save_commercial_analysis()` l.896 for the `commercial_analysis` scan. That is wrong — l.896 runs `SELECT institution_id FROM commercial_institutions WHERE institution_id=?` (an existence check), and `commercial_institutions.institution_id` is the PK (auto-indexed), so it is not a full scan. The only query that filters `commercial_analysis` by `institution_id` is `get_commercial_analysis()` at l.1106 (confirmed by grep); that column is the one with no index._

At 8–33 rows this is invisible, but the index effort was spent exactly where there is no data and omitted exactly where the reads happen. Add: `CREATE INDEX idx_cooking_household ON cooking_analysis(household_id);` `CREATE INDEX idx_reco_household ON recommendations(household_id);` `CREATE INDEX idx_commanalysis_inst ON commercial_analysis(institution_id);`

### 5. JSON blob vs the dead normalized schema — which is right? (MEDIUM)

The `fuel_breakdown` TEXT column holds a nested JSON document whose contents map *exactly* onto the unused normalized tables (verified against a live row):

```json
{ "type": "LPG", "fuels_used": ["LPG"],
  "fuel_breakdown": { "LPG": { "energy_delivered": 70.56…, "monthly_cost": 596.61…,
      "annual_emissions": 343.43…, "percentage": 100.0, "quantity": 9.18…, "unit": "kg",
      "emission_source": "https://…" } },
  "calculation_method": "dish_based",
  "selected_dishes": [ {"Dishes":"Puttu","Category":"Breakfast","stoves":"LPG"}, … ] }
```

`fuel_breakdown.LPG.*` is precisely `residential_fuel_selections` (fuel_type, energy_delivered_kwh, monthly_cost, monthly_emissions_kg, percentage_usage, monthly_quantity, quantity_unit). `selected_dishes` is precisely `residential_dish_selections` (meal_category, dish_name). So a normalized schema was designed, indexed, and given writer functions — then bypassed.

**Trade-off assessment.** For *rendering one analysis back to one user*, a JSON blob is defensible: the data is read as a whole document, has no cross-row query needs on the client path, and denormalizing avoids joins. **But this app is a survey/analytics tool** — the whole point is aggregate questions ("how many households use LPG", "average payback by district", "PM2.5 exposure distribution"). None of those are answerable in SQL today: there is **zero `json_extract`/JSON1 usage anywhere in the codebase** (grep count = 0), so the blob is opaque — every aggregate would require reading all rows into Python and parsing JSON. The blob also embeds redundant reference data (`emission_source` URL, which belongs in the reference DB) in every row. Recommendation: **normalize the fuel and dish breakdowns into the tables that already exist and start calling `save_fuel_selections`/`save_dish_selections`** (currently uncalled dead code), keeping the JSON blob only as an optional denormalized cache if replay fidelity matters. If you genuinely want document storage, at minimum use a `TEXT` column with `CHECK(json_valid(fuel_breakdown))` and query it via JSON1 — but for this analytics workload, relational normalization is the correct call.

### 6. Redundant and mis-populated columns in user_feedback (MEDIUM)

`user_feedback` carries two parallel sets of scheme-interest flags after an `ALTER`-based redesign: `png_scheme_interested`/`solar_scheme_interested`/`ujjwala_scheme_interested` **and** `support_png`/`support_solar`/`support_govt_schemes`/`support_electric_cooking`/`support_none`. The insert (`helper.py:697–724`) writes the *same* source value into overlapping columns and — a real bug — writes `support_govt_schemes` into `ujjwala_scheme_interested`:

```python
feedback_data.get('support_png', False),        # -> png_scheme_interested
feedback_data.get('support_solar', False),      # -> solar_scheme_interested
feedback_data.get('support_govt_schemes', False)# -> ujjwala_scheme_interested  (semantic mismatch)
```

Live data confirms the coupling: a row with `support_govt_schemes=1` also shows `ujjwala_scheme_interested=1`, and `support_solar=1` mirrors `solar_scheme_interested=1`. The legacy columns are dead weight that will silently diverge. Drop the `*_scheme_interested` trio (or the `support_*` set) once one is chosen as canonical, and fix the `ujjwala ← govt_schemes` mis-mapping.

### 7. Polymorphic associations instead of real relations (MEDIUM)

`alternative_recommendations(entity_id, entity_type)` and `user_feedback(entity_id, entity_type)` use a type-tag string instead of foreign keys, so referential integrity cannot be enforced, `ON DELETE CASCADE` cannot work, and the columns can't be indexed as FKs. Worse, the vocabulary is inconsistent: `user_feedback` has `CHECK(entity_type IN ('household','institution'))` while `save_alternative_recommendations()`'s contract (`helper.py:1042` docstring) declares `'residential'`/`'commercial'`. _Verification note: `save_alternative_recommendations` has **zero callers** and `alternative_recommendations` is 0 rows, so this vocabulary mismatch is currently a latent design/contract defect rather than one realized in stored data — but it is real: the moment either writer is wired up, a join across the two tables on `entity_type` would fail on the `residential`↔`household` / `commercial`↔`institution` mismatch._ Prefer two nullable FK columns (`household_id`, `institution_id`) with a `CHECK` that exactly one is set, or two separate child tables.

### 8. Inconsistent DEFAULT quoting and other drift smells (LOW)

- `households.country_code TEXT DEFAULT '+91'` (single-quoted) vs `commercial_institutions.country_code TEXT DEFAULT "+91"` (double-quoted). (`user_feedback.interest_clean_cooking DEFAULT ""` is likewise double-quoted.) Double-quoted string literals are a documented SQLite footgun — a double-quoted token that happens to match a column name is silently read as an identifier, not a string. Standardize on single quotes.
- Broken FK targets that are never exercised only because the child tables are empty: `user_analysis_history → households_new` (missing), `commercial_dish_selections → commercial_cooking_analysis` (missing) and `→ dishes_commercial` (lives in the *other* DB — cross-file FKs can never be enforced). All three referenced tables confirmed absent / cross-file.
- Dates/timestamps stored as TEXT ISO strings (`survey_date='2026-05-06'`, `typeof=text`) — acceptable in SQLite but depends entirely on format discipline in the app. (`commercial_analysis.created_at` is a related smell: `DEFAULT NULL`, and most rows are NULL because inserts never populate it.)
- TEXT UUID primary keys everywhere (36-byte random keys). Fine at this scale; at volume they cost index size and hurt insert locality vs an `INTEGER` rowid + UUID as a unique secondary column. Not worth changing now — noted for scale.

### 9. Two overlapping data-access layers (LOW, maintainability)

`database/db_helper.py` (`DatabaseHelper`, new connection per query at `get_connection()`/`get_user_connection()` l.72–92, its own `analysis_cache` DDL at l.94–103) and `helper.py` (its own `get_user_connection()` with `flask.g` pooling + `ATTACH ref` at l.223–255, and a second `analysis_cache` DDL at l.538) both manage `user_data.db` with different connection strategies and duplicate the cache-table definition. This is not a storage bug but it is how the schema drift in §1 goes unnoticed — no single source of truth for the schema. Consolidate on one layer, and move DDL into versioned migration files.

---

## Prioritized fix list

1. **(CRITICAL) Migrate `user_analysis_history`** to the schema the code expects, or fix `log_user_history` to match the on-disk columns — and stop relying on `CREATE TABLE IF NOT EXISTS` for evolution. Adopt real migrations.
2. **(HIGH) Store money as integer paise** (or round to 2dp before insert) across all cost/savings/emissions columns; stop trusting `DECIMAL(n,2)` to round.
3. **(HIGH) Add primary keys / uniqueness**: `cooking_analysis` and `commercial_analysis` → `UNIQUE(household_id)`/`UNIQUE(institution_id)` (one current record, use `INSERT … ON CONFLICT … DO UPDATE`), or an `analysis_id` run key; give `recommendations` a `(household_id, analysis_id, rank)` key. De-dupe existing rows first.
4. **(HIGH) Index the FK columns that are queried** (`cooking_analysis.household_id`, `recommendations.household_id`, `commercial_analysis.institution_id`); drop the redundant `*_type` indexes on the empty tables.
5. **(MEDIUM) Decide normalization once**: either wire up `save_fuel_selections`/`save_dish_selections` (currently uncalled) and treat the normalized tables as source of truth (recommended for an analytics tool), or delete the dead tables and add `CHECK(json_valid(...))` + JSON1 queries on the blob. Do not keep both.
6. **(MEDIUM) Collapse the duplicate feedback columns** to one canonical set and fix the `ujjwala ← govt_schemes` mis-mapping.
7. **(MEDIUM) Replace polymorphic `entity_id/entity_type`** with real nullable FKs + `CHECK`, and unify the `residential/commercial` vs `household/institution` vocabulary before either writer is wired up.
8. **(LOW) Normalize DEFAULT quoting** to single quotes; remove dead FK references to nonexistent tables; consolidate the two access layers and cache-table DDLs.

**Keep:** the reference/user two-file split and SQLite itself. Revisit Postgres only if you add concurrent writers or need server-side analytical queries at volume — neither is present today.

### Example DDL (illustrative target for cooking_analysis)

```sql
CREATE TABLE cooking_analysis (
    analysis_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    household_id       TEXT NOT NULL,
    monthly_energy_wh  INTEGER,              -- integer, no float drift
    monthly_cost_paise INTEGER,              -- money as integer paise
    calculation_method TEXT,
    kitchen_type TEXT, ventilation_quality TEXT,
    cooking_hours_daily REAL, sensitive_members INTEGER, roof_area REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(household_id),                     -- one current analysis per household
    FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
);
CREATE INDEX idx_cooking_household ON cooking_analysis(household_id);
-- fuel + dish detail go into the (currently empty) normalized tables, written per analysis_id
```

---

## 4. Database — Code & Integrity Review

*Line-by-line review of the connection management and every INSERT/UPDATE path. All items verified against the on-disk schema by replaying statements.*

## Backend / Database Code-Path Integrity Review

Scope: connection management and all INSERT/UPDATE paths into `user_data.db` across the two overlapping DB layers (`helper.py` and `database/db_helper.py`) plus `commercial_cooking.py`. All findings were verified against the on-disk schema and by replaying the actual statements on a throwaway copy of the live database.

### Verification method
- Dumped the real on-disk `CREATE TABLE` DDL. The `CREATE TABLE IF NOT EXISTS` statements in `helper.py:init_user_database()` are **no-ops** for every table that already exists, so on-disk DDL — not the Python — is the source of truth.
- Replayed the exact `log_user_history`, FK, and `INSERT OR REPLACE` statements on a copy and rolled back.
- Traced every save function to its call sites in `app.py`, `residential_cooking.py`, `commercial_cooking.py` (grep across all `.py`).
- Ran row counts, `PRAGMA index_list`, and `PRAGMA foreign_key_check` against the live DB.

---

### 1. `log_user_history()` is dead-on-arrival — 100% failure, silently swallowed  (helper.py:736-749)

The on-disk `user_analysis_history` table is:
```
history_id, household_id NOT NULL, analysis_snapshot, calculation_parameters,
system_version, analysis_timestamp, ip_address, user_agent,
session_duration_seconds, pdf_downloaded,  FOREIGN KEY(household_id) REFERENCES households_new(...)
```
but the code inserts into **`(user_id, activity_type, details)`** (helper.py:742) — none of which exist. Replaying the statement:
```
OperationalError: table user_analysis_history has no column named user_id
```
The exception is caught by a bare `except Exception` + `print()` (helper.py:746-747), so every call is a guaranteed silent failure. Callers: `save_cooking_analysis` (helper.py:689) and `save_user_feedback` (helper.py:728). This is why the table has **0 rows** (verified).

**Schema-divergence trap:** `init_user_database()` (helper.py:488-496) defines this table with the *code's* columns (`user_id, activity_type, details`) and **no FK**. Because it is `CREATE TABLE IF NOT EXISTS`, it never runs against the real DB. Consequence: on a **fresh** `user_data.db` the insert would succeed (columns match), but the FK-less fresh schema still diverges from prod — behavior differs between a developer's fresh DB and production. Reconciliation is impossible without an explicit migration.

**Fix:** Pick one schema. Either (a) migrate the table to `(user_id, activity_type, details, timestamp)` and drop the `households_new` FK, or (b) rewrite the INSERT to the real columns (`household_id, analysis_snapshot, ...`). Do not leave a swallowed-exception logger — at minimum log through the real logger, not `print`.

### 2. Commercial recommendations are silently dropped  (app.py:1315 → helper.py:751-786)

`app.py:1315` calls `helper.save_recommendations(institution_id, recommendations)` in the **commercial** flow. But `save_recommendations` guards with `SELECT household_id FROM households WHERE household_id = ?` using the *institution_id* (helper.py:758). An institution UUID is never in `households`, so `fetchone()` is `None` → **early `return` at line 762** → nothing is saved. The `recommendations` table is residential-only (FK → `households`). Verified: all 33 rows key to 7 household_ids and **zero** institution_ids appear. Commercial recommendations are never persisted, with no error surfaced to the caller.

**Fix:** Commercial recs need their own table/entity key (or the polymorphic `alternative_recommendations` table). Do not reuse a household-keyed function with an institution id.

### 3. `INSERT OR REPLACE` on a keyless table + duplicate save paths  (commercial_cooking.py:1288, helper.py:889)

`commercial_analysis` has **no PRIMARY KEY and no unique index** (`PRAGMA index_list` → `[]`; no `pk` cols). `INSERT OR REPLACE` therefore can never *replace* — it always inserts. Verified: two `INSERT OR REPLACE` for the same `institution_id` → **+2 rows** (2 → 4).

There are **two different functions named `save_commercial_analysis` with different signatures**, both writing this table:
- `helper.py:889` `save_commercial_analysis(institution_id, result)` — plain `INSERT`, omits `created_at` (→ `DEFAULT NULL`, which is why existing rows have NULL timestamps — 7 of 9 rows are NULL). Called from `app.py:1169`.
- `commercial_cooking.py:1238` `save_commercial_analysis(institution_id, kitchen_data, result)` — `INSERT OR REPLACE`, sets `created_at=CURRENT_TIMESTAMP`. Called from `commercial_cooking.py:1221`, *inside* `calculate_dish_based`.

A single **dish-based** commercial calculation hits **both** paths in one request: `app.py:1148` calls `calculate_dish_based`, which saves at `commercial_cooking.py:1221`, then `app.py:1169` saves again — appending a duplicate, timestamp-mismatched row per run (9 rows for 6 institutions).

_Verification note:_ `cooking_analysis` (residential) is also keyless and its saver `save_cooking_analysis` is reachable from two sites (`residential_cooking.py:597` and `:954`) — **but those sit in the two mutually-exclusive calc functions** (`calculate_consumption_based` vs `calculate_dish_based`), so only one runs per request. Residential duplication therefore comes from append-on-rerun / method-switch into a keyless table (8 rows), **not** a single-request double-write like the commercial dish-based path.

**Fix:** Add `institution_id`/`household_id` as PRIMARY KEY (or a UNIQUE index) so `INSERT OR REPLACE` / `ON CONFLICT ... DO UPDATE` actually upserts; then collapse the two `save_commercial_analysis` implementations into one and remove the redundant `app.py:1169` save on the dish-based path.

### 4. Foreign keys point at non-existent / cross-DB tables — `foreign_keys=ON` gives false assurance

`PRAGMA foreign_keys=ON` is set on every user-DB connection, yet several FK targets cannot be satisfied:
- `user_analysis_history.household_id → households_new` — table does not exist. Even with correct columns, an insert raises `OperationalError: no such table: main.households_new` (verified). Compounds finding #1.
- `commercial_dish_selections → commercial_cooking_analysis(analysis_id)` — parent table does not exist (verified absent), and its other FK `→ dishes_commercial` lives in the **other database** (`cooking_webapp.db` — verified present only there), which SQLite cannot enforce across the `ATTACH`ed schema.

These child tables are currently empty, so `PRAGMA foreign_key_check` on the live DB returns `[]` (verified) — no live failure — but the first write to any of them breaks.

**Fix:** Correct the FK targets (`households`, an existing analysis table) or drop the FK clauses; never model a cross-database FK.

### 5. `households.current_fuels`, `calculation_method` always `''`; `kitchen_scenario` always NULL  (app.py:350-367, helper.py:611-640)

Root cause traced end-to-end:
- `submit_household` builds `household_data` (app.py:350-367) and **never sets** `current_fuels` or `calculation_method`.
- `save_household_data` reads them with `.get('calculation_method','')` / `.get('current_fuels','')` (helper.py:635-636) → always empty string.
- `kitchen_scenario` is not in the INSERT column list at all (helper.py:611-617); it is captured *later* into session/`kitchen_data` and written only to `cooking_analysis.kitchen_type` — never back to the `households` row → permanently NULL.

Verified across all 12 rows: `calculation_method` distinct = `{''}`, `current_fuels` distinct = `{''}`, `kitchen_scenario` distinct = `{None}`. The only real record of fuels/method is the denormalized JSON blob in `cooking_analysis.fuel_breakdown`.

**Fix:** Either stop persisting these dead columns, or populate them — write `kitchen_scenario` back to `households` in `submit_kitchen`, and set `current_fuels`/`calculation_method` from the actual selection before `save_household_data`.

### 6. Two overlapping DB layers with divergent, unsafe connection policy

`helper.py` and `database/db_helper.py` each implement their own user/reference connection management, and they disagree:

| Aspect | `helper.py` | `database/db_helper.py` |
|---|---|---|
| Reference DB open mode | **read-only** URI `?mode=ro` (get_reference_connection, :219) | **read-write** `sqlite3.connect(cooking_webapp.db)` + `PRAGMA journal_mode=WAL` on it (get_connection, :76-82) |
| User connection lifetime | one shared `flask.g._database` per request, `ATTACH`es ref DB (:243) | fresh connection **per query** (_fetch_all/_fetch_one/_execute) |
| `check_same_thread` | default (`True`) | `False` |
| Busy timeout | via `connect(timeout=10.0)` (no busy_timeout PRAGMA) | `PRAGMA busy_timeout=3000` |

The most concrete risk: `db_helper.get_connection()` opens the "read-only reference database" (`DB_PATH = cooking_webapp.db`) **writable** and issues `PRAGMA journal_mode=WAL` (a write) against it. Because `db_helper._execute()` (exposed publicly as `execute_query`) runs through this connection, the read-only invariant documented for `cooking_webapp.db` is **not enforced** — a stray/erroneous `_execute()` could mutate master data.

_Verification note:_ the original draft attributed the `commercial_analysis` schema drift to this dual layer. That conflates two separate axes. The reference-DB layer split is `helper.py` vs `db_helper.py`; but `db_helper.py` never writes `commercial_analysis`. The drift in finding #3 is caused by the **two `save_commercial_analysis` functions in `helper.py` and `commercial_cooking.py`** — a different dual-ownership problem. Both are real; they are not the same root cause.

**Fix:** Consolidate on one module. Keep the reference DB strictly read-only (URI `mode=ro`) everywhere; standardize `check_same_thread` and busy-timeout settings; collapse the duplicate `save_commercial_analysis` writers (finding #3).

### 7. `save_user_feedback` swallows the error with no rollback — a latent silent-loss path  (helper.py:691-734)

`entity_type` defaults to `''` (helper.py:709), but the column has `CHECK(entity_type IN ('household','institution'))`. If an empty/unknown value ever reaches the insert it raises `IntegrityError`, which is caught by a broad `except Exception` that **logs and returns success** — no `rollback`, no re-raise (contrast with `save_household_data` at helper.py:643-645 and `save_cooking_analysis` at :682-684, which do `rollback(); raise`). The caller and user would see success while the feedback is lost.

_Verification note:_ the draft called this a "silent data loss" and "a plausible cause of the low row count (2 rows)." That is **overstated**. The only production caller, `submit_feedback`, sets `entity_type = 'institution' if is_commercial else 'household'` (app.py:773), so the CHECK is never violated in the real flow; both stored rows have `entity_type='household'`. This is a **latent robustness gap** (no rollback / re-raise, plus an unvalidated default), not an observed loss, and it does not explain the row count.

Also confirmed in this function: `ujjwala_scheme_interested` is populated from `support_govt_schemes` (helper.py:722), i.e. "government schemes" interest is silently recorded as "Ujjwala (LPG) interest"; `png_scheme_interested`←`support_png` (:720) and `solar_scheme_interested`←`support_solar` (:721) redundantly double-write their newer counterparts.

**Fix:** Validate `entity_type` before insert (or surface the error to the caller); add `rollback()` and re-raise like the sibling functions; drop or correctly map the redundant legacy scheme columns.

### 8. Dead normalized schema + never-called writers  (helper.py:927-1080)

`save_dish_selections` (helper.py:927), `save_fuel_selections` (:966), and `save_alternative_recommendations` (:1036) are fully implemented, with supporting indexes created at helper.py:548-555, but have **zero call sites** (grep across all `.py` returns only their `def` lines). The app persists this data only as JSON blobs in `*_analysis.fuel_breakdown`. Result: five tables (`residential_dish_selections`, `residential_fuel_selections`, `commercial_fuel_selections`, `commercial_dish_selections`, `alternative_recommendations`) are permanently empty (all verified at 0 rows). This is schema/code debt that obscures the real data model.

**Fix:** Either wire these writers into the save flow (and read from normalized tables), or delete the tables + functions to remove the misleading "designed but unused" surface.

### 9. f-string identifiers in SQL — not currently exploitable, but fragile  (helper.py:281/285, db_helper.py:803/821)

`ensure_table_columns` interpolates `table_name` into `PRAGMA` (helper.py:281) and `table_name`/`column_sql` into `ALTER` (helper.py:285), and `get_all_dishes`/`get_dishes_by_category` interpolate `{table}` (db_helper.py:803/821). All inputs are hard-coded literals (`'households'`, `'commercial_institutions'`, `'alternative_recommendations'`, `'user_feedback'`, and the `'dishes_residential'`/`'dishes_commercial'` ternary) — **no user-derived value reaches these**, so there is no live injection. `category_name` and all value bindings elsewhere are correctly parameterized. Flagged only as a pattern to lock down (allowlist the identifiers) before anyone wires user input into them.

### 10. Minor connection-leak on error in read helpers  (helper.py:805-823)

`get_cooking_analysis` has no `try/finally`; if `json.loads(fuel_breakdown)` raises (helper.py:818) the connection is not closed (the `close_user_connection` call at :819 is skipped). Inside a request this is harmless — the shared `flask.g` connection is skipped by `close_user_connection` (helper.py:269-271) and closed by the `teardown_appcontext` handler at app.py:258-262 — but in the script/fallback path (no app context) it leaks the connection. Same pattern in the other `get_*` readers (e.g. `get_recommendations`, helper.py:825-840). Low severity; wrap in `try/finally` or reuse `close_user_connection`.

---

## 5. CSS Review

*`static/css/style.css` / `style.min.css` (the file actually served). Contrast ratios computed with the WCAG 2.1 relative-luminance formula.*

All line numbers below refer to `static/css/style.min.css` (the file actually served); `style.css` shares the same line numbering. Contrast ratios were computed with the WCAG 2.1 relative-luminance formula.

### 1. The "minified" file is not minified, and the two CSS files have silently diverged

`templates/base.html:24` serves `style.min.css`. That file is **byte-for-byte the same size as the source** (both 42,106 bytes, 1,679 lines, fully readable — no minification happened). The only real difference between the two files is two **brand-token values**:

```
              style.css (dead)     style.min.css (SERVED)
--dark-green   #388E3C              #1b5e20
--light-green  #70C170              #4CAF50
```

Consequences:
- **`style.css` is dead source.** Any developer who edits it to fix a bug or tweak a color will see zero change on the site, because Flask serves the `.min` file. This is a silent time-sink and a correctness hazard.
- There is **no build step and no source of truth** — two hand-maintained files that have already drifted by two tokens. The header comment claims "consolidated, no duplicate rules," which is now false.
- **Fix:** pick one authoritative source, add a real minifier (e.g. `cssnano`/`lightningcss`) as a build step, and make `style.min.css` a generated artifact (git-ignored or CI-built). Short term, delete `style.css` or make it a symlink/copy of the served file so they cannot diverge. Confirm which green pair is intended — the served Material greens (`#1b5e20`/`#4CAF50`) look deliberate.

### 2. Color-contrast failures (WCAG 2.1 AA) — several on primary UI, using live template classes

| Ratio | Verdict | Selector / pair | Where it ships |
|------:|---------|-----------------|----------------|
| **1.60** | FAIL | `.stat-value` `#F2C851` on `.stats-container` `#fff` (L1118/1102) | `index.html:32,37,42` — the hero stat numbers "14+ / 4+ / 100%" are effectively invisible |
| **2.78** | FAIL | `.cta-primary` white on `--light-green #4CAF50` (L1047) | `index.html:24` — the primary homepage CTA button. (Hover `#5da55d` = 3.00, also fail. With `style.css`'s `#70C170` it would be 2.20 — worse.) |
| **1.60** | FAIL | `.btn-nav-back:hover` white on `--accent-yellow #F2C851` (L480) | 6 form pages (`energy_calculation.html`, `kitchen_profile.html`, `household_profile.html`, `commercial_*`) — the Back button label vanishes on hover |
| **3.18** | FAIL | `.lang-btn` white (0.85rem) over `rgba(255,255,255,.2)` on green strip → eff. `#4ea24e` (L288) | `base.html` language switcher, every page |
| **4.39** | AA-large-only | `--primary-green #228B22` on white — **the workhorse color** for all `h1–h6` (L138), links (L123), `.form-label` 0.9rem (L547), `.card-title`, `.chart-title` 1rem (L833), `.metric-value` | Everywhere. Passes AA only for text ≥24px (or ≥18.7px bold); **fails for form labels, body links, chart titles, h4/h5/h6.** |
| **4.39** | AA-large-only | white on `--primary-green #228B22` | `.green-strip` nav text 0.85rem (L267), `.btn-success`/`.btn-nav-next` labels 0.95rem — fail AA at these sizes |
| **4.00** | FAIL | `.alert-info` `#627578` on `#FFE7B6` (L624) | info alerts |
| **3.54** | FAIL | `.footer-copyright` `#888` on white (L1513) | footer, every page |
| **4.23** | FAIL | `--text-muted #6c757d` on `--bg-green #DEFBDD` (body gradient) | muted text over the page background |

For reference, body text `--text-grey #323232` on white/backgrounds is fine (10.5–12.8), and the alert-warning/success/danger pairs pass (4.96–8.25).

**Fixes:** darken `--stat` text to a readable color (the accent-yellow is a fill/decoration color, not a text color — use `--primary-green` or a dark neutral for the numbers). For `.cta-primary`, either use the darker green (`--primary-green`/`--dark-green`, which give 4.39/7.87) or dark text on the light-green. For `.btn-nav-back:hover`, use dark text (`--text-grey`) on the yellow, not white. Nudging `--primary-green` itself from `#228B22` to roughly `#1B7A1B`/`#1b5e20` would clear 4.5:1 for the whole design system at once and is the highest-leverage single change.

### 3. Off-by-one breakpoint gap breaks a *touch-target accessibility* rule

The file mixes two conventions: `max-width: 767.98px` (L342, header show/hide) but plain **`max-width: 767px`** for tables (L724), footer stacking (L1445/1468), icons (L1412), error page (L1543), and — critically — the **mobile touch-target rule** at L1672:

```css
@media (max-width: 767px) {          /* L1672 */
  .form-check { min-height: var(--touch-min); ... }
}
@media (min-width: 768px) { ... }
```

At any fractional viewport ~767.01–767.99 CSS px (common with browser zoom or fractional-DPR devices) **neither** `max-width:767px` nor `min-width:768px` matches, so mobile table padding, footer column-stacking, and the 44px form-check tap target all silently fail to apply. Standardize every mobile query on `max-width: 767.98px`.

### 4. No print styles — but the app produces PDF/report pages

There is **no `@media print` block at all**. The analysis/recommendation pages (comparison tables, `.metric-card`, `.recommendation-card`, `.chart-container`) are the ones users export/print, yet: card gradients + `box-shadow` + `backdrop-filter: blur` (L354) render as heavy ink or blank boxes; the `.comparison-table { min-width: 600px }` (L684) inside `overflow-x:auto` clips columns on A4; hover-lift `transform`s and the fixed green header waste the page. Add a print stylesheet that flattens backgrounds to white, drops shadows/blur/animations, forces `.table-responsive`/`.comparison-table` to `width:auto; min-width:0; overflow:visible`, and hides the header/footer/lang controls.

### 5. `!important` overuse and re-implementing Bootstrap utilities

49 `!important` declarations. A large share are utility classes that **duplicate Bootstrap 5.3** (already loaded at `base.html:13`): `.w-100` (L200), `.d-none/.d-block/.d-flex` (L202-204), `.mb-0..4`/`.mt-0..4` (L207-216), `.p-3/.p-4` (L219-220), `.text-muted` (L175), `.bg-light` (L1649), `.small` (L181), `.fw-bold`/`.fw-semibold` (L176-177). This re-declares classes Bootstrap already ships, then forces them with `!important`, creating specificity wars and dead weight. Note `.mb-3` is redefined to `1rem` and `.mb-4` to `1.5rem` (L210-211) — **different values than Bootstrap's `mb-3=1rem`/`mb-4=1.5rem`… they happen to match here, but silently shadowing framework utilities is fragile.** Remove the ones that merely restate Bootstrap; keep only the genuinely custom tokens (`.text-primary-green`, `.shadow-green`, `.fs-*`).

### 6. Duplicated show/hide rules across CSS and inline `<style>`

`.show-on-desktop` / `.show-on-mobile` are defined **twice**: in `style.min.css:337-345` and again inline in `base.html:34-53` (whose comment even says "to fix overrides"). Identical rules in two places — delete the inline copy; the stylesheet already covers it.

### 7. `overflow-x: hidden` on both `html` and `body` is a band-aid

L86 and L96 both clip horizontal overflow, with a comment admitting it hides a "side gap." This masks the real overflow bug (some child — a Bootstrap negative-gutter row or wide element — exceeds the viewport) rather than fixing it, and clipping at the root can disable `position: sticky` and interfere with scroll-anchoring/`scroll-behavior: smooth` (also set on `html`, L82). Find and constrain the offending child (candidates: `.analysis-container-custom`, full-bleed rows) and remove the root-level clip.

### 8. Design-token & maintainability notes (lower severity)

- **Token drift** (finding #1) plus many un-tokenized hardcoded hex repeated throughout: `#e9ecef` border appears ~8× (forms, institution-btn, method-card, step-number), `#f8f9fa`, hover greens `#5da55d`, and all the alert hex. Promote to `--border-muted`, `--bg-subtle`, etc.
- **`.btn-sm { min-height: 36px }`** (L496) is below the 44px touch target the rest of the file standardizes on via `--touch-min`.
- **No `prefers-reduced-motion` guard** — `fadeInUp`/`slideIn*`/`spin` animations and all the `translateY/translateX` hover transforms run unconditionally; wrap them in `@media (prefers-reduced-motion: no-preference)` for vestibular accessibility.
- **No RTL support** — the app is bilingual (en/ml). Malayalam is LTR so it's not breaking today, but the pervasive hardcoded `border-left` accents, `margin-left`, `padding-left`, and `translateX` (e.g. `.scheme-card`, `.footer-contact-links a:hover`, `.fuel-details`, alert `border-left`) would all break if any RTL locale is ever added; logical properties (`border-inline-start`, `margin-inline-start`) would future-proof cheaply.
- **Focus indicators are OK but faint on inputs:** the global `:focus-visible { outline: 3px }` (L1666) is good, but `.form-control:focus`/`.form-check-input:focus` set `outline: none` (L544, L595) and rely on a `rgba(34,139,34,0.15)` box-shadow ring — 15% alpha is very subtle for keyboard users; raise the alpha or keep an outline.
- **Header comment is inaccurate:** claims "Breakpoints: 768 / 992" but the file also uses 360px (L310) and 479px (L500-951) breakpoints, and fragments the 768px query across 10+ separate blocks.

---

## 6. HTML Template Review — Part A: Residential & Shared

## HTML / Template Review — Residential & Shared Templates

Scope: `base.html`, `index.html`, `household_profile.html`, `kitchen_profile.html`, `energy_calculation.html`, `analysis.html`, `analysis_selection.html`, `info.html`, `contact_us.html`, `error.html`. (Commercial and feedback templates excluded per assignment.) All `template:line` citations verified against the current files. Custom utility classes (`.font-medium`, `.font-semibold`, `.text-gray-900`, `.bg-gray-50`, `.analysis-container-custom`) and JS globals (`goToNextStep`, `goToPreviousStep`, `showToast`, `showLoadingOverlay`, `downloadReport`, `shareResults`) were confirmed to exist in `static/css/style.css` and `static/js/main.js`, so those references resolve.

### 1. Structural HTML validity (unclosed / mis-nested containers)

Three real markup-balance defects, in order of impact:

**a. `analysis.html` — Strategic Recommendations `.card` is never closed.** The card opens at line 261 and its `.card-body` at 262. Line 429 closes the `table-responsive`, line 433 closes the `card-body`, but there is **no `</div>` for the card itself**. The three trailing `</div>` at lines 526–528 close (in order) the recommendations card, the `.row` (line 32), and the `.container` (line 24). Net effect: the "Comparative Analysis Charts" row (435–458), the closing of `#analysis-container` (462), and the entire "Action Center" card (466–503) all render **inside** the Strategic Recommendations card. Browsers auto-balance so the page "works," but the visual grouping is wrong (charts/actions inherit the card chrome) and the markup is invalid. Fix: add a `</div>` after line 433 to close the card, and place the charts row + Action Center in their own `.col-lg-10` wrapper.

**b. `kitchen_profile.html` — `.container` (line 12) is never closed.** Inside the content block only the `col-lg-10` (line 141) and `.row` (line 142) close before `{% endblock %}` at line 144. The `<div class="container my-2.5 py-3 analysis-container-custom">` opened at line 12 has no matching `</div>`. Add one before line 144.

**c. `error.html` — no `.container` wrapper.** The page body starts with `<div class="row justify-content-center">` at line 6 with no `.container`/`.container-fluid` parent, and `base.html`'s `<main>` (line 144) provides none. Bootstrap `.row` applies negative horizontal margins, so on the 404/500/403 pages content bleeds to the viewport edge and can trigger horizontal scroll. Every other content template wraps its `.row` in `.container` (e.g. `info.html:6`, `contact_us.html:6`, `analysis_selection.html:9`); `error.html` should too.

Related Bootstrap-grid smells (non-breaking but sloppy): `household_profile.html:20` places `<form>` as a direct child of `.row` (not in a `.col-*`); `analysis.html:466` and the commented research card place `.card` directly in `.row`; `analysis_selection.html:21,44` use `.card-body` with no parent `.card`.

### 2. Accessibility

- **No `<h1>` and inverted heading order on the step pages.** `household_profile.html:13`, `energy_calculation.html:15`, `kitchen_profile.html:23`, `analysis.html:26`, and `analysis_selection.html:11` all begin the page at `<h3>` with no `<h1>` anywhere (the `base.html` brand at line 88 is a `<span>`/`<div>`, not a heading). `info.html:11` and `contact_us.html:11` correctly use `<h1>` — so it is inconsistent. Additionally, within `energy_calculation.html` the meal-card titles are `<h3>` (lines 124, 152, 178, 205) nested inside `<h4>` card titles (line 85) — the level jumps *back up* h4→h3. Analysis-panel headings are inconsistent too: LPG uses `<h4>` (`energy_calculation.html:291`) while PNG/Electricity use `<h5>` (382, 426). Establish one `<h1>` per page and never skip/reverse levels.
- **Unlabeled radio inputs.** `energy_calculation.html:39` (`#method_dish`) and `:60` (`#method_consumption`) have no associated `<label for>`; the visible text is an `<h4>` (48, 69) not tied to the control. Screen readers announce an unnamed radio. Add `aria-label` or a `<label for>`.
- **Mouse-only method cards.** `.method-card` divs (`energy_calculation.html:35,56`) get click handlers in JS (lines 662–673) but have no `role`, `tabindex`, or keydown handler, so they are not keyboard-operable; only the nested radio is. Either rely solely on the radio or add `role="button"`/`tabindex="0"`/Enter-Space handling.
- **Unlabeled `country_code` select.** `household_profile.html:46` — the `<label for="phone">` (line 44) covers only the tel input; the country-code `<select>` has no label. Add `aria-label="{{ _('Country code') }}"`.
- **Color-only status cues.** `analysis.html` risk badges (lines 132–136, 154–158, 317, 363, 411) already carry a text label plus `data-risk-rank`, which is good; but the current/alternative cost/CO₂ deltas (167–182) rely on `text-success`/`text-danger` + an arrow icon with no text alternative on the icon. The adjacent words "less/more" mitigate this — acceptable, noted for completeness.

### 3. Jinja2 correctness & templating

- **Dynamic `_(variable)` is not extractable by Babel** (feeds the translation review): `analysis.html:143` `{{ _(fuel) }}`, `:293` `{{ _(best_cost_fuel.name) }}`, `:335`, `:385`; `energy_calculation.html:108` `{{ _(fuel) }}` and the `_(...)` runtime calls on fuel names; `kitchen_profile.html:58` `{{ _(scenario.health_risk_category) }}`. pybabel cannot see these at extract time, so those DB-sourced fuel/category strings only translate if the exact literals *also* appear as constants in the catalog. This is the single most important i18n item to hand to the translation reviewer.
- **Redundant/fragile `tojson | safe` string-wrapping.** `energy_calculation.html:607,608,626` and `analysis.html:538` do `JSON.parse('{{ x | tojson | safe }}')`. Flask/Jinja `tojson` is already HTML-safe (escapes `<`,`>`,`&`,`'`), so `| safe` is redundant and the `JSON.parse('…')` wrapper is unnecessary and brittle. Prefer `const dishData = {{ dish_data | tojson }};` directly. Not an active XSS hole, but low-margin.
- **Undefined-variable resilience.** Many reads assume context keys exist: `household_data.*` (guarded with `| default`), `default_fuel_prices.*` (guarded), but `dish_data`/`fuel_label_map`/`energy_data` (`energy_calculation.html:607–626`) and `analysis.current.fuel_details` (`analysis.html:51`) are not `| default`-guarded — fine only if `StrictUndefined` is off. The dish JSON is at least guarded at runtime (`if (!dishData) return`, line 748).
- **Mangled but functional namespace loops.** `analysis.html:265–274` cram multiple `{% set %}`/`{% for %}` statements onto single lines — it works but is unreadable and error-prone; reformat.
- **Leftover debug output shipped to prod.** `analysis.html:536–539` `console.debug('DEBUG: analysis loaded', { … fuel_details … })` serializes the full fuel breakdown to the browser console on every load. Remove.
- **Dead JS referencing non-existent elements.** `analysis.html:558` scrolls to `.recommendation-card`, which exists nowhere in the template (grep-confirmed) — the scroll block (555–566) is dead. `kitchen_profile.html` `selectScenario()` (149) and `updateHealthRisk()` (203) reference `.scenario-card`, `#kitchen_type`, `#ventilation_quality`, `#health-risk-card` etc. that were removed when the dropdown replaced the cards; both functions are never called. Delete.

### 4. Forms & semantic validation

- **Energy page has no `<form>` for its inputs.** `energy_calculation.html` renders all consumption/dish inputs bare (the only `<form>` is absent); submission is manual JS via `calculateConsumption()` (1275). Consequently the `required` attributes (e.g. `#primary_fuel` line 252) are **decorative** — no native validation fires — and the CSRF hidden input at line 12 sits **outside any form** (it is read by JS at line 1138). Wrap the inputs in a `<form>` (matching `household_profile.html:20` / `kitchen_profile.html:38`) so validation and CSRF semantics are real, or document that validation is intentionally JS-only.
- `household_profile.html:54` `pattern="[0-9]{10}"` on the phone is fine but has no `inputmode="numeric"`; add for mobile keypads. Good practices already present: `novalidate` + Bootstrap `was-validated` flow, `type="email"`, `min`/`max`/`step` on numerics.

### 5. i18n readiness (hardcoded strings)

- `base.html:69` and `base.html:155` — `alt="Vasudha Foundation"` is **not** wrapped, while the sibling `alt="{{ _('EMC Kerala') }}"` (78, 156) is. Wrap for consistency.
- `base.html:101,108` — `മലയാളം` is hardcoded (acceptable as a native language name, but note it is untranslatable/unextractable).
- `analysis.html:250` — `@ 7.0%` interest and `:224` `10m²/kW`, `:229` `5.5 kWh/m²/day` are literal fragments inside otherwise-translatable sentences; the `7.0%` is also a hardcoded rate that may drift from the actual loan rate used elsewhere.
- Broadly good coverage otherwise — nearly all visible copy is wrapped in `{{ _('…') }}`, including chart `aria-label`s (`analysis.html:443,454`) and JS toast strings.

### 6. Duplication → should be macros/partials/includes

- **Meal cards** in `energy_calculation.html` (Breakfast/Lunch/Dinner/Snacks, lines 121–217) are four near-identical ~25-line blocks; drive them from a `{% for meal in [...] %}` loop or `{% macro meal_card() %}`.
- **Recommendation columns** in `analysis.html` (Most Cost-Effective / Lowest Emissions / Best Overall, lines 290–425) are three ~45-line copy-paste blocks differing only in the source object — a strong macro candidate.
- **Header/footer logo pair** (`base.html:64–81` vs `154–157`) duplicates the two `<img>`s.
- Repeated 4-column `metric-card` blocks across LPG/PNG/Electricity analysis panels (`energy_calculation.html:292–317, 383–408, 427–447`).

### 7. Inline styles / scripts & asset notes

- Very large page-specific inline `<script>` blocks (`energy_calculation.html` ~865 lines of inline JS, `analysis.html`, `household_profile.html`) plus scattered inline `style="…"` (including `!important` at `base.html:133`, `font-size` on `analysis.html:124/152/178/205`). Move page JS to `static/js/` and inline styles to CSS for CSP-friendliness and maintainability.
- **Duplicate Bootstrap Icons load:** `base.html:16` pulls the icon font from CDN *and* lines 28–32 declare a self-hosted `@font-face` for the same family — pick one.
- **No SRI on CDN assets** (`base.html:13,16,21,170`, `analysis.html:533`): add `integrity`/`crossorigin` or self-host; these are also offline-breakage points.
- **No-op spacing classes:** `my-2.5`, `mb-2.5`, `mb-1.5` (e.g. `household_profile.html:10–11`, `analysis.html:24`) are not defined in `style.css` and Bootstrap has no half-step utilities — they render as no-ops. Use `my-2`/`my-3` or define the utilities.
- `analysis_selection.html:29` uses `<p class="… flex-grow-1">&nbsp;</p>` as an alignment spacer, but the parent `.card-body` is not a flex container, so `flex-grow-1` does nothing and `font-bold` (line 29/52) is undefined (Bootstrap uses `.fw-bold`). Cosmetic hack that should be replaced with proper flex layout.

### Positives worth keeping
`<meta viewport>` present (`base.html:6`), dynamic `<html lang="{{ get_locale() }}">` (line 2), meaningful `alt`/`aria-label` on most images/canvases, `width`/`height` on logos to prevent CLS, `fetchpriority`/`loading` hints, `<picture>`/WebP for the Vasudha logo, CSRF tokens in the two real forms, and progress-bar ARIA (`base.html:132–134`).

---

## 7. HTML Template Review — Part B: Commercial & Feedback

## Commercial & Feedback Templates — HTML/Template Review

Files reviewed: `templates/commercial_selection.html`, `commercial_kitchen_profile.html`, `commercial_energy_calculation.html`, `commercial_analysis.html`, `feedback.html`, `feedback_success.html`. Cross-checked against `templates/base.html` and `static/js/main.js`.

Overall the markup is Bootstrap-5-consistent, CSRF tokens are present on every form, and **static** user-visible text is almost entirely wrapped in `{{ _() }}` (a heuristic scan found no unwrapped visible sentences). No duplicate static `id` attributes exist in any file. The problems cluster around (1) one genuine functional form bug in `feedback.html`, (2) a large block of chart JavaScript in `commercial_analysis.html` that duplicates `main.js`, (3) an unbalanced `<div>` / grid-nesting defect in the same file, (4) dynamic-value i18n gaps, and (5) console debug output that leaks user PII.

### 1. Functional bug — required fields inside a collapsed section block the "No" submission path (feedback.html)

`feedback.html` is the highest-value finding. The form (L32) has **no `novalidate`**, and the Verify-Contact inputs are `required`:

```
L225  <input ... id="name"  name="name"  value="{{ user_name }}" required ...>
L234  <input ... id="email" name="email" value="{{ user_email }}" required ...>
L243  <input ... id="phone" name="phone" value="{{ user_phone }}" required ...>
```

These live inside `#consentAndSupport`, which is hidden purely visually via inline CSS `max-height:0; opacity:0` (L80–81) — not `display:none`, not `hidden`, not `aria-hidden`. The JS reveal only runs when Question A = "yes" (L280–288). When the user picks **"No, I have enough information"**, the submit handler (L314–337) does **not** `preventDefault`, so native constraint validation fires against the still-`required`, empty, zero-height `name`/`email`/`phone` fields. Chrome/Firefox then throw *"An invalid form control … is not focusable"* and silently block submission — the user clicks Submit and nothing happens. The collapsed inputs also remain in the tab order and reachable by screen readers.

**Fix:** mirror the pattern used in `commercial_selection.html` (`toggleSolarArea`, L431–442) — toggle the `required` attribute on when the section is revealed and off when collapsed — or hide the section with `display:none`/`hidden`, or add `novalidate` to the form and rely on the existing JS validation (which already only checks these three when interest === 'yes', L324–333).

### 2. `commercial_analysis.html` duplicates ~470 lines of chart JS already in main.js

`static/js/main.js` already defines `chartInstances` (L338), `initializeCharts` (L349), `createEnhancedCostChart` (L382), `createEnhancedEmissionsChart` (L443), `createEnhancedHealthChart` (L497), `createEnhancedRadarChart` (L578), and calls `initializeCharts()` automatically when `#costChart` exists (L124–126). `commercial_analysis.html` re-defines the *entire* pipeline inline (L814–1305), shadowing the `main.js` copies. The residential `analysis.html` correctly reuses `main.js` and defines **none** of these (`createEnhancedCostChart` count = 0 there vs 2 in commercial). This is ~470 lines of drift-prone duplication: any fix to chart behaviour must now be made twice, and the two copies can silently diverge.

**Fix:** delete the inline chart functions from `commercial_analysis.html` and rely on `main.js` (as residential does), or extract the shared logic into one module both pages include.

### 3. Unbalanced `<div>` and Bootstrap grid violation (commercial_analysis.html)

A tag-balance scan of the content block (comments and Jinja stripped) shows **76 `<div>` opens vs 75 closes** — exactly one unclosed. Tracing it: the `.col-lg-10#analysis-container` (L47) is closed at L638; the `<!-- end container -->` comment at L773 actually closes the `.row` (L46), leaving the outer `<div class="container">` (L35) **unclosed**. As a consequence, the **Action Center card (L702–739) sits directly inside `.row justify-content-center` with no `.col-*` wrapper** — a grid violation (the card does not receive column sizing/gutters and the row's flex layout is thrown off). Browsers auto-recover, but the output is invalid HTML5 and the layout is affected.

**Fix:** add the missing `</div>` for the container, and wrap the Action Center card in a `<div class="col-lg-10">` (matching the analysis column).

### 4. Chart guard requires health data although the page has no health/radar canvas (commercial_analysis.html)

The template only renders `#costChart` (L621) and `#emissionsChart` (L632) — there is no `#healthChart` or `#radarChart` canvas. Yet `handleChartDataSuccess` (L866) bails to `showChartError('No chart data is available…')` unless `hasCost && hasEmissions && hasHealth` are all truthy. `createEnhancedHealthChart`/`createEnhancedRadarChart` then no-op on the missing canvases. So if `/api/chart_data` omits `health_comparison`, the **entire chart area shows an error even though cost and emissions could render**. Related dead references in the same file: `summaryCost`/`summaryHealth`/`summaryGrade` (L1069–1075) and `.recommendation-card` scroll target (L802) — none of these elements exist in the markup.

**Fix:** relax the guard to require only the data that has a canvas, and remove the dead health/radar/summary/scroll code.

### 5. i18n — dynamic values passed to `_()` and untranslated DB values

Static strings are well covered, but several places feed **runtime/DB values** into gettext, which `pybabel extract` cannot collect (they only translate if the exact literal happens to exist elsewhere in the catalog):

- `commercial_kitchen_profile.html` L48 `{{ _(scenario.health_risk_category) }}`
- `commercial_energy_calculation.html` L113 `{{ _(fuel.fuel_name) }}`
- `commercial_analysis.html` L304 `{{ _(fuel) }}`, L462 `{{ _(best_cost_fuel.name) }}`, L505, L559

Separately, institution types and dish names are rendered **raw/untranslated**: `institution.institution_type` (`commercial_energy_calculation.html` L27; `commercial_analysis.html` L43, L55) and `dish_info.dish` / `meal` (L94, L241). In Malayalam these appear in English. `localize_db_label(...)` is used correctly for districts and scenario names — the same approach (or explicit `_en`/`_ml` columns) should be applied here.

### 6. Console debug output leaks user PII and payloads

Every template emits `console.debug`/`console.log` with data objects. Most notably `feedback.html` L9–14 dumps `user_name`, `user_email`, `user_phone` to the browser console; `commercial_energy_calculation.html` (L13–17, L593, L611) and `commercial_analysis.html` (L26–33, L781) dump full institution/analysis payloads. Values go through `| tojson` so this is not an XSS vector (Flask's `tojson` escapes `<`,`>`,`&`), but PII/console noise should not ship to production.

**Fix:** strip the debug scripts (or gate them behind a debug flag) before release.

### 7. Accessibility gaps (all commercial forms)

- **Radio/checkbox groups lack `<fieldset>`/`<legend>`.** The institution-type group (`commercial_selection.html` L43–84) is headed by an `<h4>`; the "All fuels" group (`commercial_energy_calculation.html` L101) uses a bare `<label>` that is associated with no control. Group semantics are lost for screen readers.
- **Method cards not keyboard-operable.** `.method-card` divs (`commercial_energy_calculation.html` L45–79) have click handlers (JS L760) but no `tabindex`/`role`/keydown; the inner radio is still focusable, so this is a mouse-only enhancement rather than a hard block.
- **Custom-styled radios + `invalid-feedback`.** In `commercial_selection.html` the `.invalid-feedback` for institution type (L85) is a sibling of the button grid with visually-hidden radios; Bootstrap's `:invalid ~ .invalid-feedback` reveal will not fire reliably here.
- **Decorative `<i class="bi …">` icons** throughout lack `aria-hidden="true"`.

### 8. Lower-severity / maintainability

- **Method radios sit outside the form.** In `commercial_energy_calculation.html` the `calculation_method` radios (L48–68) precede `<form id="energyForm">` (L85); submission relies entirely on JS-injected hidden inputs (L650–655, L715–720). Works, but fragile.
- **`current_fuel_mix` double-submitted** in dish mode: the checkboxes (L107) are inside the form *and* re-added as hidden inputs (L658–665), so the field is sent twice.
- **`innerHTML` built from DB dish names** via template literals without escaping (`commercial_energy_calculation.html` L878–888, L1043–1064; `commercial_analysis.html` uses server-side rendering so is fine). Low XSS risk since names are reference-DB-sourced, but the pattern is unsafe.
- **Phone `pattern="[0-9]{10}"`** is enforced (`commercial_selection.html` L132, `feedback.html` L244) even when a non-India `country_code` (+971/+44/+1) is selected — those numbers are not 10 digits.
- **Inline styles scattered** (`feedback.html` L55/68/81/122…, `commercial_energy_calculation.html` L53/54/73, `commercial_analysis.html` L129) should move to CSS classes.
- **Large commented-out dead markup** in `commercial_analysis.html` (Health Impact L639–700, Research Info L742–772) bloats the file and should be deleted (git history preserves it).
- **External CDNs** (`Chart.js` in both analysis templates; Bootstrap/Bootstrap-Icons/Google Fonts in `base.html`) mean the tool degrades offline and complicates any future CSP — informational, but relevant for a government-facing tool.

---

## 8. Internationalization (i18n) Review

## Internationalization (Flask-Babel) Review

Scope: `messages.pot`, `translations/{en,ml}/LC_MESSAGES/messages.{po,mo}`, `babel.cfg`, `config.py`, `app.py` (locale selection), `templates/base.html` (switch mechanism), `static/css/style.css`, `pdf_generator.py`, plus the two existing review docs in `review/`. All counts below were produced by re-parsing the catalogs and by a **fresh `pybabel extract` from the current working tree**, not taken from the review docs.

### Headline: the catalog is in excellent shape; the gaps are outside the catalog

The gettext catalog itself is essentially clean and current. The real i18n weaknesses now live in the surrounding plumbing: no Malayalam webfont, a hardcoded-English flash layer that is also never rendered, and a completely separate PDF translation layer that bypasses gettext.

---

### 1. Coverage — real counts

| Metric | Value |
| --- | --- |
| Translatable messages in `messages.pot` | **589** (excluding header) |
| `translations/en` entries | 589, **all `msgstr` empty** (intentional fallback) |
| `en` compiled `.mo` entries | 0 (English UI renders the msgid / template source directly) |
| `translations/ml` entries | 589 |
| `ml` empty / untranslated `msgstr` | **0 → 100% translated** |
| `ml` `fuzzy` flags | **0** (git-history "removed fuzzy for app title" is confirmed done) |
| `ml` msgids missing vs `.pot` | 0 |
| `ml` orphan msgids (in `ml` but not in `.pot`) | **0** — the 37 orphans from the earlier review are gone |
| `ml` deliberately left in Latin script | 8 — `CO₂`, `English`, `LPG`, `PNG`, `email@example.com`, and the 3 income bands `50,000 - 70,000` / `70,000 - 1,00,000` / `1,00,000 - 1,50,000` (all justified) |
| `ml` mixed-script entries | 57 — **all intentional** (embedded `CO₂ PV BESS GHI EMI PM2.5 WHO LPG PNG SCM kg μg/m³`); now a consistent policy, no longer the inconsistency the old review flagged |

**Drift check (most important):** `app.py` and every template are shown as modified (`M`) in `git status`, so I re-extracted a fresh `.pot` from the current source and diffed msgids against the committed catalog:

```
committed messages.pot ids : 589
fresh-extracted ids        : 589
in source but not in catalog: 0
in catalog but not in source: 0
```

The catalog matches the working tree exactly — the modifications were re-extracted and translated. There is **no stale-catalog drift right now.**

### 2. Correctness — placeholders

I scanned every `msgid`/`msgstr` in both catalogs for `%s` / `%(name)s` / `{}` style placeholders:

- **0 entries in the entire catalog contain any placeholder.**

Consequence: there is **zero risk of a placeholder-mismatch runtime error** — the class of bug the task asked me to hunt for does not exist here. The flip side is that the app never uses parameterized gettext: dynamic values (₹ amounts, kWh, counts) are concatenated *outside* `_()`. That is functional but limits how naturally Malayalam grammar/number-ordering can be rendered, and is worth keeping in mind if any sentence ever needs an interpolated value.

### 3. `.mo` freshness

I decoded the binary `.mo` files and compared them entry-by-entry to the `.po`:

| Locale | `.po` non-empty | `.mo` entries | Differences |
| --- | --- | --- | --- |
| `ml` | 589 | 589 | **0** |
| `en` | 0 | 0 | 0 |

Compiled catalogs are **fully up to date**. Compilation is manual via `compile_translations.bat` (`pybabel compile -d translations -l en` / `-l ml`). It is **not wired into any deploy/CI step**, and `babel.cfg` has **no JavaScript extractor** (only `[python:]` and `[jinja2:]`). Both are latent drift risks flagged (correctly) by `APPLIED_CHANGES.md §6`.

### 4. Language switch mechanism

- `templates/base.html:2` → `<html lang="{{ get_locale() }}">`. `get_locale()` (`app.py:84`) returns only `'en'`/`'ml'` (guarded by `normalize_language` + `request.accept_languages.best_match(['en','ml'])`), so **`<html lang>` is always a valid, correct BCP-47 value.**
- Selection order is sound: `session['language']` → `Accept-Language` best match → `'en'`. Legacy `'hi'` is mapped to `'ml'`.
- Switch is a JS `fetch('/set_language/<lang>')` then `location.reload()` (`base.html:176`); `/set_language` (`app.py:290`) writes the session and returns JSON.
- Minor robustness notes: (a) the dropdown items use `onclick=...; href="#"`, so **switching requires JavaScript** — no `<noscript>`/server-rendered fallback link; (b) it is a **state-changing GET**; (c) Babel is initialized twice — `babel = Babel(app)` (`app.py:49`) and again `babel.init_app(app, locale_selector=get_locale)` (`app.py:214`); redundant but harmless, and the `locale_selector` is correctly wired on the second call.

### 5. Malayalam font handling — real gap

- `base.html` loads only **Poppins** (Latin-only) from Google Fonts; the body `font-family` is `'Poppins', …, sans-serif` (`style.css:91`). Poppins has no Malayalam glyphs, so **all Malayalam text falls through to whatever Malayalam font the user's OS happens to have** — tofu boxes on devices without one.
- `style.css:187` defines `.malayalam-text { font-family:'Noto Sans Malayalam','Poppins' }`, but (a) that family is **never loaded** (no `@font-face`, no Google-Fonts request), and (b) the class is **used 0 times** in `templates/` — it is dead code.
- There is **no `:lang(ml)` / `html[lang="ml"]` CSS rule** to select a Malayalam face for the whole document. For a bilingual public tool this is the most impactful gap: the entire second language relies on client-side font luck.

### 6. Hardcoded / untranslated strings

| Location | Issue |
| --- | --- |
| `app.py:1014,1031,1061,1115,1164,1179,1287` | ~7 `flash(...)` error strings hardcoded in English, **not wrapped in `_()`** (e.g. `'Error processing kitchen profile'`, `'Calculation failed'`). Compounding this, **`get_flashed_messages` is rendered in 0 templates**, so these flashes are never shown at all on the redirect path (the AJAX path uses `jsonify` with `str(e)`). Both an i18n gap and dead error feedback. |
| `templates/base.html:69`, `:155` | `alt="Vasudha Foundation"` hardcoded ×2 — not wrapped. Malayalam screen-reader users get English alt text. (`EMC Kerala` and the cooking-tool logo alt *are* wrapped, so `APPLIED_CHANGES.md`'s "three logo alt attributes wrapped" is only partly true.) |
| `templates/base.html:7` | `<meta name="description">` is hardcoded English, never localized (SEO + i18n). The `<title>` *is* localized. |
| `static/js/main.js` | Not covered by `babel.cfg`; contains `textContent=`/`innerHTML=` assignments (low volume). Template-embedded JS strings are fine — they are `{{ _() }}`-wrapped and do get extracted. |
| `templates/household_profile.html:136` | The `<span>to</span>` the earlier review flagged is now **inside an HTML comment** (dead) — income is a proper `_()`-wrapped `<select>`. Not a live issue. |

### 7. Second, non-gettext translation layer — `pdf_generator.py`

`pdf_generator.py` has **0 `_()` calls**, **1,553 hardcoded Malayalam characters**, its own `SUPPORTED_REPORT_LOCALES`, and **no `flask_babel`/`gettext` import**. The downloadable report is bilingual but its wording is **completely independent of the catalogs**, so terminology *will* drift from the web UI (e.g. UI "വിശകലനം" vs a hand-written "വിലയിരുത്തൽ" in the PDF; "Kerala" vs "Keralam"). Not a catalog defect, but a genuine consistency/maintenance liability. Already noted in `APPLIED_CHANGES.md §6`.

### 8. What the existing review docs already cover (not re-litigated here)

- `review/TRANSLATION_REVIEW.md` is the **pre-application** analysis measured against a **stale `.pot`**; its figures (628/622/665, 12 fuzzy, 37 orphans, 97 whitespace-damaged msgids) are historical and **now superseded** — I confirmed independently they no longer hold.
- `review/APPLIED_CHANGES.md` is the post-application record (589/589 in sync, 0 fuzzy, whitespace-damaged msgids cleaned, terminology unified) and already recommends: move `pdf_generator.py` onto gettext, add a JS extractor, and add extract+compile to deploy. My pass **confirms** all of these with fresh measurement and **adds**: no Malayalam webfont / dead `.malayalam-text`, the 7 hardcoded+unrendered flash strings, the 2 hardcoded Vasudha `alt`s, the hardcoded meta description, the double Babel init, and the zero-placeholder (no-crash-risk) fact.

### 9. Remediation plan (priority order)

1. **Bundle a Malayalam webfont.** Add `Noto Sans Malayalam` (or Manjari) via `@font-face`/Google-Fonts and set it for `html[lang="ml"] body` (or apply the existing `.malayalam-text` rule at the locale level). Highest user-visible impact.
2. **Wrap and surface flash messages.** Wrap the ~7 `app.py` flash strings in `_()`, add them to the catalog, and render `get_flashed_messages()` in `base.html` — or delete the dead flash+redirect branches if the AJAX path is authoritative.
3. **Localize the remaining head/alt strings.** Wrap `alt="Vasudha Foundation"` (`base.html:69,155`) and localize the `<meta name="description">` (`base.html:7`).
4. **Unify the PDF layer.** Move `pdf_generator.py` onto `flask_babel`/`gettext`, or at minimum align its terminology and "Kerala" spelling with the catalog.
5. **Harden the build.** Add `pybabel extract` + `compile` (and a JS extractor line in `babel.cfg`) to the deploy step so catalogs and `.mo` cannot drift; today it is entirely manual.
6. **Minor:** drop the redundant `Babel(app)` at `app.py:49`; add a `<noscript>` fallback for language switching; keep `session['language']` preserved across `clear_application_journey` (already done).

---

## 9. Consolidated Remediation Roadmap

Sequenced so that foundational fixes (migrations, a single access layer) land before the work that depends on them. Effort is a rough T-shirt size (S/M/L).

### Phase 0 — Stop the bleeding (hours)
| Fix | Finding | Effort |
|---|---|---|
| Repair `log_user_history` / migrate `user_analysis_history`; replace the swallowed `print` with real logging | #1 (critical) | S |
| Fix the feedback-form "No" submission path (toggle `required` with the collapsed section, or add `novalidate`) | HTML-Com #1 | S |
| Make `style.min.css` a copy/symlink of the authoritative source (stop the silent divergence) until a build step exists | CSS #1 | S |
| Remove `console.debug`/`console.log` that leak user PII and payloads to the browser | HTML #6 (both) | S |
| Fix the contrast failures on hero stats, primary CTA, and Back-button hover | CSS #2 | S |

### Phase 1 — Database foundations (days)
| Fix | Finding | Effort |
|---|---|---|
| Introduce **real migrations** (a `schema_migrations` table + ordered scripts); retire `CREATE TABLE IF NOT EXISTS` as an evolution tool | DB-Arch #1 | M |
| Add **primary keys / uniqueness** to `cooking_analysis`, `commercial_analysis`, `recommendations`; de-dupe existing rows; switch to `ON CONFLICT … DO UPDATE` | DB-Arch #3, DB-Code #3 | M |
| **Index** `cooking_analysis.household_id`, `recommendations.household_id`, `commercial_analysis.institution_id`; drop the redundant indexes on empty tables | DB-Arch #4 | S |
| Store **money as integer paise** (or round to 2 dp before insert) across all cost/savings/emissions columns | DB-Arch #2 | M |
| **Consolidate to one data-access layer**; keep the reference DB strictly read-only everywhere; collapse the two `save_commercial_analysis` functions; give commercial recommendations their own persistence path | DB-Code #2, #3, #6 | M |

### Phase 2 — Data model decision (days)
| Fix | Finding | Effort |
|---|---|---|
| **Normalize** the fuel/dish breakdowns: wire up `save_fuel_selections`/`save_dish_selections` and read from the normalized tables — *or* delete the dead tables and adopt `CHECK(json_valid(...))` + JSON1 queries. Pick one. | DB-Arch #5, DB-Code #8 | L |
| Collapse the redundant `user_feedback` columns to one canonical set; fix the `ujjwala ← govt_schemes` mis-mapping | DB-Arch #6, DB-Code #7 | S |
| Replace polymorphic `entity_id/entity_type` with real nullable FKs + `CHECK`; unify the `residential/commercial` vs `household/institution` vocabulary | DB-Arch #7 | M |
| Populate or drop the always-empty `households.current_fuels` / `calculation_method` / `kitchen_scenario` columns | DB-Code #5 | S |

### Phase 3 — Front-end & accessibility (days)
| Fix | Finding | Effort |
|---|---|---|
| Add a real CSS **build step** (`lightningcss`/`cssnano`); make `style.min.css` a generated, git-ignored artifact | CSS #1 | M |
| Raise the core brand green to clear AA (≈`#1b5e20`), fix remaining contrast pairs, standardize the `767.98px` breakpoint, add a `@media print` stylesheet and a `prefers-reduced-motion` guard | CSS #2–4, #8 | M |
| Fix unbalanced markup in `analysis.html` and `commercial_analysis.html`; add the missing `.container` to `error.html`; wrap energy-page inputs in a real `<form>` | HTML-Res #1,#4, HTML-Com #3 | M |
| Establish one `<h1>` per page and correct heading order; label the method radios and `country_code` select; make method cards keyboard-operable | HTML #2 (both) | M |
| De-duplicate the ~470 lines of chart JS in `commercial_analysis.html` against `main.js`; extract repeated markup into Jinja macros; delete dead JS/markup | HTML-Com #2, HTML-Res #3,#6 | M |

### Phase 4 — i18n hardening (days)
| Fix | Finding | Effort |
|---|---|---|
| **Bundle a Malayalam webfont** (`Noto Sans Malayalam`/Manjari) via `@font-face`, applied to `html[lang="ml"]` — highest user-visible i18n impact | i18n #5 | S |
| Wrap and actually render the ~7 hardcoded `flash()` strings (or delete the dead redirect branches); localize the two logo `alt`s and the meta description | i18n #6 | S |
| Move `pdf_generator.py` onto gettext (or align its terminology with the catalog) so the report doesn't drift from the UI | i18n #7 | L |
| Add `pybabel extract` + `compile` (and a JS extractor line in `babel.cfg`) to the deploy step; drop the redundant `Babel(app)` init | i18n #3, #9 | S |

---

## Appendix A — `user_data.db` table inventory

13 user tables (+ `sqlite_sequence`). Row counts are from the live database at audit time.

| Table | Rows | Primary key | Purpose | Principal issues |
|---|---:|---|---|---|
| `households` | 12 | `household_id` (TEXT/UUID) | Residential user profiles | ALTER-based schema drift; `current_fuels`/`calculation_method` always `''`, `kitchen_scenario` always NULL; `"+91"`/`'+91'` quoting drift |
| `cooking_analysis` | 8 | **none** | Residential energy results | No PK → duplicate rows; FK column unindexed; real data buried in `fuel_breakdown` JSON blob |
| `recommendations` | 33 | **none** | Residential recommendations | No PK/`rank`/`created_at` → multiple analysis runs mixed together; unindexed FK column |
| `commercial_institutions` | 6 | `institution_id` (TEXT/UUID) | Institution profiles | ALTER-based schema drift; `"+91"` double-quoted default |
| `commercial_analysis` | 9 | **none** | Commercial energy results | No PK → `INSERT OR REPLACE` can't replace; single request double-writes; `created_at` NULL for most rows |
| `user_feedback` | 2 | `feedback_id` (TEXT/UUID) | Feedback + scheme interest | Redundant `*_scheme_interested` vs `support_*` columns; `ujjwala ← govt_schemes` mis-mapping; latent `CHECK` + no-rollback path |
| `analysis_cache` | 12 | `cache_key` | Server-side analysis cache | OK; but its DDL is duplicated across both helper modules |
| `residential_dish_selections` | **0** | `selection_id` | (designed) dish selections | Dead: writer function exists but has no callers |
| `residential_fuel_selections` | **0** | `fuel_selection_id` | (designed) fuel selections | Dead: writer function exists but has no callers |
| `commercial_fuel_selections` | **0** | `fuel_selection_id` | (designed) fuel selections | Dead: never written |
| `commercial_dish_selections` | **0** | `id` | (designed) dish selections | Dead; FK → missing `commercial_cooking_analysis` and cross-DB `dishes_commercial` |
| `alternative_recommendations` | **0** | `recommendation_id` | (designed) alt-fuel recs | Dead; polymorphic `entity_id/entity_type`; vocabulary mismatch |
| `user_analysis_history` | **0** | `history_id` | Activity/analysis log | 🔴 100% write failure (column mismatch); FK → non-existent `households_new` |

**Pattern:** the 6 tables that hold real data all have structural gaps (missing PKs, unindexed FKs, JSON blobs); the 6 "clean" normalized tables are all **empty dead code**; and the 1 logging table is **broken**.

---

## Appendix B — Verification methodology

- **Schema truth:** dumped the on-disk `CREATE TABLE` DDL via `SELECT sql FROM sqlite_master` — because `init_user_database()` uses `CREATE TABLE IF NOT EXISTS`, the Python DDL is a **no-op** for existing tables, so the on-disk schema (not the code) is authoritative.
- **Statement replay:** the `log_user_history` insert, the FK targets, and the `INSERT OR REPLACE` behavior were replayed on a throwaway copy of `user_data.db` and rolled back — e.g. `log_user_history` reproducibly raises `OperationalError: table user_analysis_history has no column named user_id`, and two `INSERT OR REPLACE` for the same `institution_id` produced **+2 rows**, proving the keyless-table no-op.
- **Call-graph tracing:** every `save_*` function was traced to its call sites across `app.py`, `residential_cooking.py`, `commercial_cooking.py` via grep; "dead code" claims (`save_fuel_selections`, `save_dish_selections`, `save_alternative_recommendations`) were confirmed by finding **only the `def` lines**.
- **Integrity probes:** `PRAGMA index_list`, `PRAGMA foreign_key_check`, row counts, and `typeof()` on stored money values were run against the live databases.
- **Adversarial correction:** the verification pass **downgraded or corrected** several first-pass claims — e.g. the money-equality hazard was re-stated precisely (float representation error, not the int/real storage-class mix), the `commercial_analysis` scan line was corrected, and the feedback "silent data loss" claim was reduced to a *latent* robustness gap because the only production caller sets a valid `entity_type`. Those corrections are folded into the sections above.
- **i18n counts** were produced by re-parsing the catalogs and running a **fresh `pybabel extract`** from the current working tree (all templates and `app.py` show as modified in git), confirming 589 msgids with zero drift.
- **CSS contrast** ratios were computed from the actual hex tokens in the served `style.min.css` against the template classes that use them.

---

*Generated by an 8-agent parallel audit (6 specialist reviewers + 2 adversarial database verifiers). Per-dimension findings and verifier verdicts are preserved in the structured data behind this report.*
