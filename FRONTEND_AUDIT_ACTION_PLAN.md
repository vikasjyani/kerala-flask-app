# Frontend Audit Action Plan

## Scope

This plan covers the follow-up frontend work found during the HTML/CSS/mobile audit. The calculation rounding fix is separate and already handled at backend output boundaries.

## Current Findings

1. `templates/base.html` still loads Bootstrap CSS, Bootstrap Icons CSS, Google Fonts, and Bootstrap JS from CDNs.
2. `templates/analysis.html` and `templates/commercial_analysis.html` load Chart.js from CDN.
3. `static/fonts/bootstrap-icons.woff2` is already present, but the matching local `bootstrap-icons.css` is not wired as the main icon stylesheet.
4. `static/fonts/NotoSansMalayalam-*.ttf` and DejaVu fonts are already present, but `Poppins` is still requested from Google Fonts.
5. Large result tables are responsive through horizontal scrolling, but mobile reading is still not ideal for comparison-heavy data.
6. Global `overflow-x: hidden` rules in `static/css/style.css` can hide layout defects instead of exposing them during QA.
7. Some old JavaScript in `templates/kitchen_profile.html` references removed fields and should be deleted or reconnected.

## Recommended Implementation Plan

### Phase 1: Self-Host External Dependencies

Files to change:

- `templates/base.html`
- `templates/analysis.html`
- `templates/commercial_analysis.html`
- `static/vendor/bootstrap/`
- `static/vendor/bootstrap-icons/`
- `static/vendor/chartjs/`
- `static/fonts/`

Steps:

1. Add local Bootstrap CSS and JS files under `static/vendor/bootstrap/`.
2. Add local Bootstrap Icons CSS under `static/vendor/bootstrap-icons/` and point its `@font-face` to `static/fonts/bootstrap-icons.woff2`.
3. Add local Chart.js under `static/vendor/chartjs/`.
4. Replace CDN links in templates with `url_for('static', filename='...')`.
5. Either self-host Poppins font files or remove the Google Fonts dependency and use a local font stack.
6. Verify that icons, modals, dropdowns, tooltips, and charts render on all pages.

### Phase 2: Mobile Result Presentation

Files to change:

- `templates/analysis.html`
- `templates/commercial_analysis.html`
- `static/css/style.css`
- `static/css/style.min.css`

Steps:

1. Keep desktop comparison tables unchanged.
2. Add mobile-only stacked comparison cards for current fuel and alternatives.
3. Hide wide tables on small screens only where card layout gives a better reading experience.
4. Test at `390x844`, `430x932`, `768x1024`, and desktop widths.

### Phase 3: CSS Overflow Cleanup

Files to change:

- `static/css/style.css`
- `static/css/style.min.css`

Steps:

1. Audit global `overflow-x: hidden` usage.
2. Remove broad hiding rules where possible.
3. Apply overflow handling only to known scrollable components like tables and carousels.
4. Re-run mobile screenshots and check `document.documentElement.scrollWidth <= window.innerWidth`.

### Phase 4: Dead JavaScript Cleanup

Files to change:

- `templates/kitchen_profile.html`
- `static/js/main.js`
- `static/js/main.min.js`

Steps:

1. Remove or update `updateHealthRisk()` references to old field names.
2. Confirm no console errors on kitchen profile, energy calculation, analysis, feedback, and commercial pages.
3. Keep `main.js` and `main.min.js` synchronized after any JS change.

## Verification Checklist

Run these after each phase:

1. `python -m py_compile app.py helper.py residential_cooking.py commercial_cooking.py database\db_helper.py`
2. Start the app with `python app.py`.
3. Visit residential and commercial flows on desktop and mobile widths.
4. Confirm no horizontal page overflow except intentional table/card scroll areas.
5. Confirm browser console has no errors.
6. Confirm charts render after Chart.js is local.
7. Confirm language dropdown, Bootstrap icons, tooltips, modals, and navigation confirmation still work.
