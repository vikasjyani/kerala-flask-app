"""
One-time migration for user_data.db — remediates the audit findings:

  * user_analysis_history  : broken schema (writer used non-existent columns) -> rebuilt to (user_id, activity_type, details, timestamp)
  * cooking_analysis       : no PK -> surrogate analysis_id PK + UNIQUE(household_id) + created_at (dedup existing rows)
  * commercial_analysis    : no PK -> surrogate analysis_id PK + UNIQUE(institution_id) + created_at (dedup existing rows)
  * recommendations        : no PK -> surrogate id PK + rank + created_at
  * user_feedback          : drop redundant *_scheme_interested legacy columns (keep canonical support_* set)
  * commercial_dish_selections : broken FK (missing/cross-db tables) -> rebuilt to reference commercial_institutions
  * indexes                : add on the FK columns actually queried

Idempotent: re-running is a no-op once the target schema is in place.
Usage:  python migrate_user_db.py [path_to_user_data.db]
"""
import sqlite3
import sys


def _cols(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def _has_pk(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[5] for r in cur.fetchall())  # r[5] = pk flag


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()
    changed = []

    # --- 1. user_analysis_history: rebuild to the schema the code actually writes ---
    cols = _cols(cur, "user_analysis_history")
    if "activity_type" not in cols:
        cur.execute("DROP TABLE IF EXISTS user_analysis_history")
        cur.execute("""
            CREATE TABLE user_analysis_history (
                history_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT,
                activity_type TEXT NOT NULL,
                details      TEXT,
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        changed.append("user_analysis_history rebuilt")

    # --- 2. cooking_analysis: add surrogate PK + UNIQUE(household_id) + created_at ---
    if not _has_pk(cur, "cooking_analysis"):
        cur.execute("ALTER TABLE cooking_analysis RENAME TO cooking_analysis_old")
        cur.execute("""
            CREATE TABLE cooking_analysis (
                analysis_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                household_id       TEXT NOT NULL,
                monthly_energy_kwh DECIMAL(8,2),
                calculation_method TEXT,
                kitchen_type       TEXT,
                ventilation_quality TEXT,
                cooking_hours_daily DECIMAL(4,2),
                sensitive_members  INTEGER,
                roof_area          DECIMAL(6,2),
                current_monthly_cost DECIMAL(8,2),
                fuel_breakdown     TEXT,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(household_id),
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            )
        """)
        # keep only the most-recent row per household (highest rowid)
        cur.execute("""
            INSERT INTO cooking_analysis
                (household_id, monthly_energy_kwh, calculation_method, kitchen_type,
                 ventilation_quality, cooking_hours_daily, sensitive_members, roof_area,
                 current_monthly_cost, fuel_breakdown)
            SELECT household_id, monthly_energy_kwh, calculation_method, kitchen_type,
                   ventilation_quality, cooking_hours_daily, sensitive_members, roof_area,
                   current_monthly_cost, fuel_breakdown
            FROM cooking_analysis_old
            WHERE rowid IN (SELECT MAX(rowid) FROM cooking_analysis_old GROUP BY household_id)
        """)
        cur.execute("DROP TABLE cooking_analysis_old")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cooking_household ON cooking_analysis(household_id)")
        changed.append("cooking_analysis rebuilt (+PK, +UNIQUE, deduped)")

    # --- 3. commercial_analysis: add surrogate PK + UNIQUE(institution_id) + created_at ---
    if not _has_pk(cur, "commercial_analysis"):
        cur.execute("ALTER TABLE commercial_analysis RENAME TO commercial_analysis_old")
        cur.execute("""
            CREATE TABLE commercial_analysis (
                analysis_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                institution_id     TEXT NOT NULL,
                monthly_energy_kwh DECIMAL(10,2),
                monthly_cost       DECIMAL(10,2),
                annual_emissions   DECIMAL(10,2),
                calculation_method TEXT,
                fuel_breakdown     TEXT,
                primary_fuel       TEXT,
                health_risk_score  DECIMAL(5,2),
                environmental_grade TEXT,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(institution_id),
                FOREIGN KEY (institution_id) REFERENCES commercial_institutions(institution_id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            INSERT INTO commercial_analysis
                (institution_id, monthly_energy_kwh, monthly_cost, annual_emissions,
                 calculation_method, fuel_breakdown, primary_fuel, health_risk_score,
                 environmental_grade, created_at)
            SELECT institution_id, monthly_energy_kwh, monthly_cost, annual_emissions,
                   calculation_method, fuel_breakdown, primary_fuel, health_risk_score,
                   environmental_grade, COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM commercial_analysis_old
            WHERE rowid IN (SELECT MAX(rowid) FROM commercial_analysis_old GROUP BY institution_id)
        """)
        cur.execute("DROP TABLE commercial_analysis_old")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_commanalysis_inst ON commercial_analysis(institution_id)")
        changed.append("commercial_analysis rebuilt (+PK, +UNIQUE, deduped)")

    # --- 4. recommendations: add surrogate PK + rank + created_at ---
    if not _has_pk(cur, "recommendations"):
        cur.execute("ALTER TABLE recommendations RENAME TO recommendations_old")
        cur.execute("""
            CREATE TABLE recommendations (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                household_id             TEXT,
                recommended_solution     TEXT,
                recommendation_score     DECIMAL(5,2),
                estimated_monthly_savings DECIMAL(8,2),
                estimated_payback_years  DECIMAL(4,2),
                health_risk_score        DECIMAL(5,2),
                environmental_grade      TEXT,
                rank                     INTEGER,
                created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            )
        """)
        # rank by score within household (highest score = rank 1)
        cur.execute("""
            INSERT INTO recommendations
                (household_id, recommended_solution, recommendation_score,
                 estimated_monthly_savings, estimated_payback_years, health_risk_score,
                 environmental_grade, rank)
            SELECT household_id, recommended_solution, recommendation_score,
                   estimated_monthly_savings, estimated_payback_years, health_risk_score,
                   environmental_grade,
                   ROW_NUMBER() OVER (PARTITION BY household_id
                                      ORDER BY recommendation_score DESC) AS rank
            FROM recommendations_old
        """)
        cur.execute("DROP TABLE recommendations_old")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reco_household ON recommendations(household_id)")
        changed.append("recommendations rebuilt (+PK, +rank, +created_at)")

    # --- 5. user_feedback: drop redundant *_scheme_interested legacy columns ---
    cols = _cols(cur, "user_feedback")
    if "png_scheme_interested" in cols:
        cur.execute("ALTER TABLE user_feedback RENAME TO user_feedback_old")
        cur.execute("""
            CREATE TABLE user_feedback (
                feedback_id             TEXT PRIMARY KEY,
                entity_id               TEXT NOT NULL,
                entity_type             TEXT NOT NULL CHECK(entity_type IN ('household', 'institution')),
                name                    TEXT,
                email                   TEXT,
                phone                   TEXT,
                interest_clean_cooking  TEXT DEFAULT '',
                allow_authority_contact BOOLEAN DEFAULT 0,
                support_solar           BOOLEAN DEFAULT 0,
                support_electric_cooking BOOLEAN DEFAULT 0,
                support_png             BOOLEAN DEFAULT 0,
                support_govt_schemes    BOOLEAN DEFAULT 0,
                support_none            BOOLEAN DEFAULT 0,
                feedback_text           TEXT,
                submitted_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            INSERT INTO user_feedback
                (feedback_id, entity_id, entity_type, name, email, phone,
                 interest_clean_cooking, allow_authority_contact, support_solar,
                 support_electric_cooking, support_png, support_govt_schemes,
                 support_none, feedback_text, submitted_at)
            SELECT feedback_id, entity_id, entity_type, name, email, phone,
                   COALESCE(interest_clean_cooking, ''), allow_authority_contact, support_solar,
                   support_electric_cooking, support_png, support_govt_schemes,
                   support_none, feedback_text, submitted_at
            FROM user_feedback_old
        """)
        cur.execute("DROP TABLE user_feedback_old")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_entity ON user_feedback(entity_id, entity_type)")
        changed.append("user_feedback rebuilt (dropped 3 redundant legacy columns)")

    # --- 6. commercial_dish_selections: fix broken FK targets ---
    cur.execute("SELECT sql FROM sqlite_master WHERE name='commercial_dish_selections'")
    row = cur.fetchone()
    if row and "commercial_cooking_analysis" in (row[0] or ""):
        cur.execute("DROP TABLE commercial_dish_selections")  # 0 rows, safe
        cur.execute("""
            CREATE TABLE commercial_dish_selections (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                institution_id TEXT NOT NULL,
                meal_category TEXT,
                dish_name     TEXT,
                meal_type     VARCHAR(50),
                fuel_used     VARCHAR(100),
                quantity_kg   REAL,
                servings      INTEGER,
                energy_kwh    REAL,
                cost          REAL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (institution_id) REFERENCES commercial_institutions(institution_id) ON DELETE CASCADE
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_commercial_dish_institution ON commercial_dish_selections(institution_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_commercial_dish_category ON commercial_dish_selections(meal_category)")
        changed.append("commercial_dish_selections rebuilt (fixed broken FK targets)")

    conn.commit()
    # integrity check
    cur.execute("PRAGMA foreign_key_check")
    fk_problems = cur.fetchall()
    cur.execute("PRAGMA integrity_check")
    integ = cur.fetchone()[0]
    conn.close()
    return changed, fk_problems, integ


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "user_data.db"
    changed, fk_problems, integ = migrate(path)
    print(f"DB: {path}")
    print("integrity_check:", integ)
    print("foreign_key_check problems:", fk_problems if fk_problems else "none")
    if changed:
        print("Changes applied:")
        for c in changed:
            print("  -", c)
    else:
        print("No changes needed (already migrated).")
