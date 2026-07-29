# Audit Remediation — Status

Branch: `fix/full-audit-remediation`. Backups of the databases, translations and CSS are in `.audit_backup/` (git-ignored). Every phase was verified (migration integrity check, save-path smoke test, template compile + DOM balance, route smoke test incl. Malayalam) and committed separately.

**Verified working after all changes:** app imports (26 routes); `/`, `/info`, `/contact_us`, `/analysis_selection`, `/household_profile`, `/commercial_selection`, `/commercial_energy_calculation` all return 200; language switch to `ml` renders `<html lang="ml">` with Malayalam text; 404 renders the fixed `error.html`.

## Commits
| Commit | Scope |
|---|---|
| `fix(db)` | Database schema + integrity + normalization (migration + `helper.py`, `db_helper.py`, `commercial_cooking.py`, `app.py`) |
| `fix(db)` (2) | `get_recommendations` try/finally; this status doc |
| `fix(css)` | WCAG contrast, real minification, print + reduced-motion, breakpoints |
| `fix(frontend+i18n)` | Feedback-form bug, template structure, a11y, Malayalam catalog |
| `fix(frontend+i18n)` (2) | Chart-JS de-duplication, a11y labels, JS extractor |

---

## Fixed (56 of 72 findings)

### Second pass (deferred items now completed)
- 🟡 **`commercial_analysis.html` duplicated ~470 lines of chart JS** — removed (507 lines); the page now relies on `static/js/main.js` exactly like residential `analysis.html`. This also fixed the **over-strict chart guard** (cost+emissions now render even when health data is absent; missing health/radar canvases are skipped safely by `main.js`).
- 🔵 **Unlabeled method radios** (`energy_calculation`, `commercial_energy_calculation`) and **`country_code` selects** (`household_profile`, `commercial_selection`) — `aria-label` added.
- 🔵 **`babel.cfg`** — added a `[javascript:]` extractor for future gettext calls in JS.
- 🟡 **Institution types & fuel names rendered untranslated** — added `institution_type_label()` (maps stored values incl. the `Hotel`→"Hotel/Restaurant" / `Factory`→"Factory Canteen" value-vs-label mismatch to the catalog labels) and routed the commercial displays through it; the fuel checkbox now uses `localize_db_label(fuel.fuel_name, fuel.fuel_name_ml)`. (Dish-name localization still deferred — see below.)
- 🟡 **`energy_calculation.html` inputs not in a `<form>`** — wrapped in `<form onsubmit="return false;">` so CSRF + `required` are semantically valid; submit stays JS-driven (calculate button is `type="button"`), so no behavior change.

### First pass

### Database — architecture & integrity (all Critical + High + most Medium)
- 🔴 **`user_analysis_history` 100% write failure** — table rebuilt to the schema the code writes (`user_id, activity_type, details, timestamp`); `log_user_history` now records (verified: table populates) and logs via the real logger, not `print`.
- 🟠 **Money as raw floats** — all cost/savings/emissions/energy values rounded to 2 dp before insert via `_money()` (per your choice).
- 🟠 **No primary keys** — `cooking_analysis` & `commercial_analysis` got surrogate PKs + `UNIQUE(household_id|institution_id)` (existing dup rows deduped: 8→7, 9→5); `recommendations` got `id` PK + `rank` + `created_at`. Saves now upsert (`ON CONFLICT DO UPDATE`).
- 🟠 **Indexes on empty tables, hot columns unindexed** — added `idx_cooking_household`, `idx_reco_household`, `idx_commanalysis_inst`, `idx_commercial_dish_*`.
- 🟠 **`log_user_history` column mismatch** — fixed (see above).
- 🟠 **Commercial recommendations silently dropped** — new `save_commercial_recommendations()` persists them to `alternative_recommendations` (`entity_type='institution'`); `app.py` now calls it.
- 🟠 **`INSERT OR REPLACE` on keyless table + double-write** — `commercial_analysis` now upserts on the UNIQUE key; the duplicate in-function save in `commercial_cooking.py` was removed (single save path via `app.py`).
- 🟡 **JSON blob vs dead normalized tables** — per your choice, the normalized tables are now the **source of truth**: `save_cooking_analysis`/`save_commercial_analysis` populate `residential/commercial_fuel_selections` and `*_dish_selections` (replace-on-save). Verified: rows now written.
- 🟡 **Redundant feedback columns + mis-mapping** — dropped `png/solar/ujjwala_scheme_interested`; `save_user_feedback` writes the canonical `support_*` set only, validates `entity_type`, and rolls back + re-raises on error.
- 🟡 **Broken FK targets** — `commercial_dish_selections` rebuilt to reference `commercial_institutions`; `user_analysis_history`'s dangling `households_new` FK removed.
- 🟡 **Reference DB writable** — `db_helper.get_connection()` now opens `cooking_webapp.db` read-only (`mode=ro`).
- 🟡 **`households` summary columns always empty** — `current_fuels`, `calculation_method`, `kitchen_scenario` now populated on save.
- 🔵 **Read-helper connection leak** — `get_cooking_analysis` / `get_recommendations` wrapped in `try/finally`.

### CSS (all High + most Medium/Low)
- 🟠 `style.min.css` is now a **real minified build** (43 KB → 28 KB) generated from `style.css`; they no longer diverge.
- 🟠 **Contrast fixes**: `--primary-green` `#228B22`→`#1b7a1b` (5.46:1); `.stat-value`, `.cta-primary` (+hover), `.btn-nav-back:hover`, `.lang-btn` all now ≥ 4.5:1.
- 🟡 Breakpoints standardized to `767.98px`; added `@media print`; added `@media (prefers-reduced-motion: reduce)`; `.btn-sm` touch target 36→44 px.

### HTML templates
- 🟠 **feedback.html "No" path bug** — `required` name/email/phone were trapped in a collapsed section, silently blocking submit. Now `required` + `inert` toggle with the reveal.
- 🟡 **Unbalanced markup** — `commercial_analysis.html` (unclosed `.container`; Action Center wrapped in a `.col-lg-10`) and `kitchen_profile.html` (unclosed `.container`) fixed; DOM div balance verified.
- 🟡 **error.html** wrapped in `.container` (no longer bleeds to viewport edges).
- 🔵 **23 `console.debug`/`console.log('DEBUG')`** calls removed across templates (were leaking user/institution PII to the console).
- 🔵 `kitchen_profile.html` no-op `my-2.5` → `my-2`.

### i18n
- 🟡 **Malayalam webfont** — Noto Sans Malayalam loaded and applied to `html[lang="ml"]` (Poppins had no Malayalam glyphs).
- 🟡 **Flash messages** — 7 commercial `flash()` strings wrapped in `_()`; `get_flashed_messages()` now rendered in `base.html` (previously flashes were never shown anywhere).
- 🔵 Localized `<meta description>` and the two `Vasudha Foundation` alts.
- ⚪ Removed the redundant `Babel(app)` double-init.
- Re-extracted catalogs; added Malayalam for the 9 new strings; cleared 5 fuzzy flags; recompiled `.mo` (Malayalam 100% translated).

---

## Deferred (16 findings) — with rationale

These are genuine but were **not** applied because each is either a large refactor with real regression risk on a working government-facing app, or low-value polish better done as its own reviewed change. None is a correctness bug in the paths exercised today.

| Finding | Why deferred |
|---|---|
| 🟡 **Dish names** in `commercial_analysis.html` rendered untranslated (`dish_info.dish`) | The `selected_dishes` blob stores only English names; localizing needs the calculation pipeline (`commercial_cooking.py`) to persist the `dish_name_ml` alongside each selected dish. Institution types + fuel names **were** localized this pass. |
| 🟡 `pdf_generator.py` is a second, non-gettext translation layer | 1,500+ hardcoded Malayalam chars; moving it onto gettext is a large, self-contained task. |
| 🟡 `analysis.html` charts/Action-Center visually nested inside the Recommendations card | DOM is balanced and renders; the fix is a cosmetic re-grouping with layout-regression risk. |
| 🟡 Heading order / missing `<h1>` on step pages | A11y polish across many templates; low functional impact, touches visible structure. |
| 🟡 Polymorphic `entity_id/entity_type` → real FKs | Code now uses a consistent `household`/`institution` vocabulary; converting to dual nullable FKs + CHECK is a schema change with little practical gain at this scale. |
| 🔵 Method-card keyboard operability; radio/checkbox `fieldset`/`legend`; decorative-icon `aria-hidden`; per-page `<h1>`/heading order | Remaining a11y polish. Control **labels** (method radios, `country_code`) are now done; the rest is numerous small edits best done as a dedicated a11y pass (the `<h1>` change touches visible structure). |
| 🔵 Duplicated markup → Jinja macros (meal cards, recommendation columns, logos) | Refactor-only; no behavior change; risk of subtle rendering diffs. |
| 🔵 SRI on CDN assets; duplicate Bootstrap-Icons load (CDN + self-host) | Requires choosing a CSP/offline strategy; informational. |
| 🔵 `overflow-x:hidden` on html/body masks a real overflow child | Needs finding the offending element; the clip is currently harmless. |
| 🔵 RTL logical properties; un-tokenized hex; `!important`/Bootstrap-utility duplication | Maintainability; no user-facing bug (app is LTR). |
| 🔵 f-string SQL identifiers | Confirmed not exploitable (all identifiers are hard-coded literals); flagged only as a pattern. |
| 🔵 Language switch requires JS / state-changing GET; add JS extractor to `babel.cfg`; wire extract+compile into deploy | Build/deploy hardening, out of app scope. |
| ⚪ Catalog uses no parameterized gettext | Informational (means zero placeholder-mismatch risk). |

To restore pre-change state: `git checkout main`, or restore a DB from `.audit_backup/`.
