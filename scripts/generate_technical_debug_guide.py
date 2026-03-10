#!/usr/bin/env python3
"""Generate a DB-backed technical debug guide for the cooking analysis app."""

from __future__ import annotations

import copy
import logging
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from itertools import combinations, cycle
from pathlib import Path
from typing import Any

import pandas as pd
from werkzeug.datastructures import MultiDict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import debug_logger
logging.disable(logging.CRITICAL)
debug_logger.logger.disabled = True

import commercial_cooking
import helper
import residential_cooking
from database.db_helper import SYSTEM_PARAMETER_ALIASES
from helper import db_helper

OUTPUT_PATH = ROOT / "TECHNICAL_DEBUG_GUIDE.md"


def disable_logging() -> None:
    logging.disable(logging.CRITICAL)
    debug_logger.logger.disabled = True


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt_number(value: Any, digits: int = 2) -> str:
    return f"{as_float(value):,.{digits}f}"


def fmt_money(value: Any) -> str:
    return f"Rs {fmt_number(value, 2)}"


def fmt_percent(value: Any, digits: int = 1) -> str:
    return f"{as_float(value):.{digits}f}%"


def fmt_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def append_table(lines: list[str], headers: list[str], rows: list[list[Any]]) -> None:
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(fmt_text(cell) for cell in row) + " |")
    lines.append("")


def emissions_value(payload: dict[str, Any]) -> float:
    if not isinstance(payload, dict):
        return 0.0
    return as_float(
        payload.get("annual_emissions")
        or payload.get("annual_co2")
        or payload.get("annual_co2_kg")
        or payload.get("annual_emissions_kg")
        or 0
    )


def non_empty_subsets(items: list[str]) -> list[tuple[str, ...]]:
    result: list[tuple[str, ...]] = []
    for size in range(1, len(items) + 1):
        result.extend(combinations(items, size))
    return result


def ui_dish_fuel_pool() -> list[str]:
    return [fuel["fuel_name"] for fuel in db_helper.get_all_fuels(True) if fuel["fuel_name"] != "Solar + BESS"]


def mix_label(items: tuple[str, ...] | list[str]) -> str:
    return " + ".join(items)


def get_reference_efficiency(reference: dict[str, Any], fuel_name: str, default: float = 0.0) -> float:
    return as_float(reference.get("default_efficiencies", {}).get(fuel_name, default))


def assignment_count_for_subset(subset_size: int, dish_count: int) -> int:
    return subset_size ** dish_count


def total_assignment_patterns(fuel_pool_size: int, dish_count: int) -> int:
    total = 0
    for size in range(1, fuel_pool_size + 1):
        total += len(list(combinations(range(fuel_pool_size), size))) * (size ** dish_count)
    return total


def requested_param_status(name: str, default: Any) -> dict[str, Any]:
    candidates = [name]
    alias = SYSTEM_PARAMETER_ALIASES.get(name)
    if alias and alias not in candidates:
        candidates.append(alias)

    for candidate in candidates:
        row = db_helper.fetch_one(
            """
            SELECT param_name, param_value, param_type
            FROM system_parameters
            WHERE param_name = ?
              AND (valid_to IS NULL OR valid_to >= date('now'))
            """,
            (candidate,),
        )
        if row:
            source = "direct" if candidate == name else f"alias:{candidate}"
            return {
                "requested": name,
                "resolved_name": row["param_name"],
                "resolved_value": row["param_value"],
                "source": source,
            }

    return {
        "requested": name,
        "resolved_name": "-",
        "resolved_value": default,
        "source": "fallback",
    }


def get_reference_snapshot() -> dict[str, Any]:
    conn = db_helper.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ft.fuel_name, ef.co2_factor, ef.pm25_factor
            FROM fuel_types ft
            LEFT JOIN emission_factors ef ON ef.fuel_id = ft.fuel_id
            WHERE ft.is_active = 1
              AND (ef.valid_to IS NULL OR ef.valid_to >= date('now'))
            ORDER BY ft.display_order
            """
        )
        fuel_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT scenario_type, scenario_name, combined_factor, health_risk_category
            FROM kitchen_scenarios
            ORDER BY scenario_type, display_order
            """
        )
        scenario_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT group_type, size_min, size_max, efficiency_factor
            FROM group_cooking_efficiency
            ORDER BY group_type, size_min
            """
        )
        group_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT institution_type, meal_type, calories_normal, calories_heavy, calories_light
            FROM institution_meal_calories
            ORDER BY institution_type, meal_type
            """
        )
        meal_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT d.district_name, ft.fuel_name, fp.pricing_category, fp.unit_price,
                   fp.subsidized_unit_price, fp.unit_name, fp.valid_from, fp.valid_to
            FROM fuel_unit_pricing fp
            JOIN districts d ON d.district_id = fp.district_id
            JOIN fuel_types ft ON ft.fuel_id = fp.fuel_id
            WHERE d.district_name = ?
            ORDER BY ft.display_order, fp.pricing_category
            """,
            ("Thiruvananthapuram",),
        )
        pricing_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT meal_type, intensity, energy_percent
            FROM meal_energy_distribution
            ORDER BY intensity, meal_type
            """
        )
        meal_distribution_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT grade_letter, co2_per_serving_kg, co2_per_member_daily_kg,
                   annual_per_member_kg, label, applicable_to
            FROM environmental_grades
            ORDER BY grade_id
            """
        )
        grade_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT te.area_type, te.stove_type, ft.fuel_name, te.efficiency
            FROM thermal_efficiencies te
            JOIN fuel_types ft ON ft.fuel_id = te.fuel_id
            WHERE te.valid_to IS NULL OR te.valid_to >= date('now')
            ORDER BY te.area_type, ft.display_order, te.stove_type
            """
        )
        thermal_rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    watched_params = [
        requested_param_status("LPG_CALORIFIC_VALUE_KWH_PER_KG", 12.8),
        requested_param_status("LPG_DOMESTIC_CYLINDER_WEIGHT_KG", 14.2),
        requested_param_status("LPG_COMMERCIAL_CYLINDER_WEIGHT_KG", 19.0),
        requested_param_status("PNG_CALORIFIC_VALUE_KWH_PER_SCM", 10.2),
        requested_param_status("BIOMASS_ENERGY_CONTENT", 4.5),
        requested_param_status("ELECTRICITY_RESIDENTIAL_RATE", 6.5),
        requested_param_status("ELECTRICITY_COMMERCIAL_RATE", 9.5),
        requested_param_status("PNG_FIXED_CHARGE_MONTHLY", 0),
        requested_param_status("PNG_METER_RENT_MONTHLY", 0),
        requested_param_status("Keralam_SOLAR_GHI", 5.59),
        requested_param_status("SOLAR_SYSTEM_EFF", 0.85),
        requested_param_status("Keralam_WEATHER_FACTOR", 0.88),
    ]

    return {
        "fuel_rows": fuel_rows,
        "scenario_rows": scenario_rows,
        "group_rows": group_rows,
        "meal_rows": meal_rows,
        "pricing_rows": pricing_rows,
        "meal_distribution_rows": meal_distribution_rows,
        "grade_rows": grade_rows,
        "thermal_rows": thermal_rows,
        "watched_params": watched_params,
        "default_efficiencies": helper.DEFAULT_EFFICIENCIES,
    }


def base_residential_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    household = {
        "name": "Debug Household",
        "district": "Thiruvananthapuram",
        "area_type": "Urban",
        "household_size": 4,
        "monthly_income": 25000,
        "lpg_subsidy": "Yes",
        "electricity_tariff": 6.5,
        "loan_interest_rate": 7.0,
        "loan_tenure": 5,
        "main_priority": "balanced",
        "solar_willingness": "Yes",
        "solar_rooftop_area": 80,
    }
    kitchen = {
        "kitchen_scenario": "Chimney",
        "kitchen_type": "Chimney",
        "cooking_hours_daily": 3,
        "sensitive_members": 1,
        "roof_area_available": 80,
        "breakfast_timing": "late",
        "ventilation_quality": "Average",
    }
    return household, kitchen


def commercial_profiles() -> OrderedDict[str, dict[str, Any]]:
    return OrderedDict(
        [
            (
                "School",
                {
                    "institution_type": "School",
                    "institution_name": "Debug School",
                    "district": "Thiruvananthapuram",
                    "area_type": "Urban",
                    "servings_per_day": 200,
                    "working_days": 26,
                    "electricity_tariff": 9.5,
                    "solar_willing": "Yes",
                    "available_roof_area": 350,
                    "loan_interest_rate": 7.0,
                    "loan_tenure": 5,
                    "main_priority": "balanced",
                },
            ),
            (
                "Anganwadi",
                {
                    "institution_type": "Anganwadi",
                    "institution_name": "Debug Anganwadi",
                    "district": "Thiruvananthapuram",
                    "area_type": "Urban",
                    "servings_per_day": 80,
                    "working_days": 26,
                    "electricity_tariff": 9.5,
                    "solar_willing": "Yes",
                    "available_roof_area": 120,
                    "loan_interest_rate": 7.0,
                    "loan_tenure": 5,
                    "main_priority": "balanced",
                },
            ),
            (
                "Hotel",
                {
                    "institution_type": "Hotel",
                    "institution_name": "Debug Hotel",
                    "district": "Thiruvananthapuram",
                    "area_type": "Urban",
                    "servings_per_day": 150,
                    "working_days": 30,
                    "electricity_tariff": 9.5,
                    "solar_willing": "Yes",
                    "available_roof_area": 500,
                    "loan_interest_rate": 7.0,
                    "loan_tenure": 5,
                    "main_priority": "balanced",
                },
            ),
            (
                "Factory",
                {
                    "institution_type": "Factory",
                    "institution_name": "Debug Factory",
                    "district": "Thiruvananthapuram",
                    "area_type": "Urban",
                    "servings_per_day": 300,
                    "working_days": 26,
                    "electricity_tariff": 9.5,
                    "solar_willing": "Yes",
                    "available_roof_area": 600,
                    "loan_interest_rate": 7.0,
                    "loan_tenure": 5,
                    "main_priority": "balanced",
                },
            ),
            (
                "Community Kitchen",
                {
                    "institution_type": "Community Kitchen",
                    "institution_name": "Debug Community Kitchen",
                    "district": "Thiruvananthapuram",
                    "area_type": "Urban",
                    "servings_per_day": 250,
                    "working_days": 30,
                    "electricity_tariff": 9.5,
                    "solar_willing": "Yes",
                    "available_roof_area": 450,
                    "loan_interest_rate": 7.0,
                    "loan_tenure": 5,
                    "main_priority": "balanced",
                },
            ),
        ]
    )


def commercial_kitchen(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "kitchen_scenario": "Chimney",
        "kitchen_type": "Chimney",
        "cooking_hours_daily": 6,
        "sensitive_members": 2,
        "roof_area_available": profile.get("available_roof_area", 300),
        "breakfast_timing": "early",
        "ventilation_quality": "Average",
    }


def first_residential_dishes() -> OrderedDict[str, dict[str, Any]]:
    dishes = OrderedDict()
    for row in db_helper.get_all_dishes("residential"):
        category = row["category_name"]
        if category in ("Breakfast", "Lunch", "Dinner", "Snacks") and category not in dishes:
            dishes[category] = row
    return dishes


def first_commercial_dishes(institution_type: str) -> OrderedDict[str, dict[str, Any]]:
    dishes = OrderedDict()
    for row in db_helper.get_all_dishes("commercial"):
        if row.get("institution_type") != institution_type:
            continue
        category = row["category_name"]
        if category in ("Breakfast", "Lunch", "Dinner", "Snacks") and category not in dishes:
            dishes[category] = row
    return dishes


def canonical_residential_dishes(target_count: int = 5) -> list[dict[str, Any]]:
    rows = [row for row in db_helper.get_all_dishes("residential") if row["category_name"] in ("Breakfast", "Lunch", "Dinner", "Snacks")]
    picks: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for category in ("Breakfast", "Lunch", "Dinner", "Snacks"):
        for row in rows:
            if row["category_name"] != category or row["dish_name"] in used_names:
                continue
            picks.append(row)
            used_names.add(row["dish_name"])
            break

    for row in rows:
        if len(picks) >= target_count:
            break
        if row["dish_name"] in used_names:
            continue
        picks.append(row)
        used_names.add(row["dish_name"])
    return picks


def canonical_commercial_dishes(institution_type: str, target_count: int = 5) -> list[dict[str, Any]]:
    rows = [
        row
        for row in db_helper.get_all_dishes("commercial")
        if row.get("institution_type") == institution_type and row["category_name"] in ("Breakfast", "Lunch", "Dinner", "Snacks")
    ]
    picks: list[dict[str, Any]] = []
    used_names: set[str] = set()

    for category in ("Breakfast", "Lunch", "Dinner", "Snacks"):
        for row in rows:
            if row["category_name"] != category or row["dish_name"] in used_names:
                continue
            picks.append(row)
            used_names.add(row["dish_name"])
            break

    for row in rows:
        if len(picks) >= target_count:
            break
        if row["dish_name"] in used_names:
            continue
        picks.append(row)
        used_names.add(row["dish_name"])
    return picks


def build_residential_dish_subset_examples(
    household: dict[str, Any],
    kitchen: dict[str, Any],
    meal_types: dict[str, str],
) -> dict[str, Any]:
    base_dishes = canonical_residential_dishes()
    fuel_pool = ui_dish_fuel_pool()
    subset_rows = []

    for subset in non_empty_subsets(fuel_pool):
        assignments = []
        form_pairs: list[tuple[str, str]] = [
            ("calculation_method", "dish"),
            ("breakfast_type", meal_types["breakfast_type"]),
            ("lunch_type", meal_types["lunch_type"]),
            ("dinner_type", meal_types["dinner_type"]),
        ]
        fuel_cycle = cycle(subset)
        for dish_row in base_dishes:
            fuel = next(fuel_cycle)
            assignments.append(f"{dish_row['dish_name']} -> {fuel}")
            form_pairs.append((f"{dish_row['category_name'].lower()}_dishes", dish_row["dish_name"]))
            form_pairs.append((f"{dish_row['dish_name']}_fuel", fuel))
            form_pairs.append(("current_fuel_mix", fuel))

        result = residential_cooking.calculate_dish_based(
            MultiDict(form_pairs),
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
            language="en",
        )
        subset_rows.append(
            {
                "fuel_mix": subset,
                "assignment": assignments,
                "selected_fuels": len(subset),
                "dish_count": len(base_dishes),
                "assignment_count": assignment_count_for_subset(len(subset), len(base_dishes)),
                "result": result,
            }
        )

    return {"base_dishes": base_dishes, "fuel_pool": fuel_pool, "subset_rows": subset_rows}


def build_commercial_dish_subset_examples(
    institution: dict[str, Any],
    kitchen: dict[str, Any],
    meal_types: dict[str, str],
) -> dict[str, Any]:
    base_dishes = canonical_commercial_dishes(institution["institution_type"])
    fuel_pool = ui_dish_fuel_pool()
    subset_rows = []

    for subset in non_empty_subsets(fuel_pool):
        assignments = []
        form_pairs: list[tuple[str, str]] = [
            ("calculation_method", "dish"),
            ("servings_per_day", str(institution["servings_per_day"])),
            ("working_days_per_month", str(institution["working_days"])),
            ("breakfast_type", meal_types["breakfast_type"]),
            ("lunch_type", meal_types["lunch_type"]),
            ("dinner_type", meal_types["dinner_type"]),
        ]
        fuel_cycle = cycle(subset)
        assigned_fuels: list[str] = []
        for dish_row in base_dishes:
            fuel = next(fuel_cycle)
            assigned_fuels.append(fuel)
            assignments.append(f"{dish_row['dish_name']} -> {fuel}")
            form_pairs.append((f"{dish_row['category_name'].lower()}_dishes", dish_row["dish_name"]))
            form_pairs.append((f"{dish_row['dish_name']}_fuel", fuel))
            form_pairs.append(("current_fuel_mix", fuel))

        unused_fuels = [fuel for fuel in subset if fuel not in assigned_fuels]
        result = commercial_cooking.calculate_dish_based(
            MultiDict(form_pairs),
            copy.deepcopy(institution),
            copy.deepcopy(kitchen),
            None,
        )
        subset_rows.append(
            {
                "fuel_mix": subset,
                "assignment": assignments,
                "selected_fuels": len(subset),
                "dish_count": len(base_dishes),
                "assignment_count": assignment_count_for_subset(len(subset), len(base_dishes)),
                "unused_fuels": unused_fuels,
                "result": result,
            }
        )

    return {"base_dishes": base_dishes, "fuel_pool": fuel_pool, "subset_rows": subset_rows}


def form_input_text(payload: dict[str, Any] | MultiDict, include_blank: bool = False) -> str:
    if hasattr(payload, "items"):
        try:
            pairs = list(payload.items(multi=True))  # type: ignore[arg-type]
        except TypeError:
            pairs = list(payload.items())  # type: ignore[assignment]
    else:
        pairs = []

    parts = []
    for key, value in pairs:
        if not include_blank and value in ("", None):
            continue
        parts.append(f"{key}={value}")
    return "<br>".join(parts)


def result_fuel_breakdown(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fuel_details = result.get("fuel_details", {})
    if not isinstance(fuel_details, dict):
        return {}

    fuel_breakdown = fuel_details.get("fuel_breakdown")
    if isinstance(fuel_breakdown, dict) and fuel_breakdown:
        return {fuel: details for fuel, details in fuel_breakdown.items() if isinstance(details, dict)}

    nested_entries = {
        fuel: details
        for fuel, details in fuel_details.items()
        if isinstance(details, dict)
    }
    return nested_entries


def fuel_breakdown_summary(result: dict[str, Any]) -> str:
    parts = []
    for fuel_name, details in result_fuel_breakdown(result).items():
        delivered = details.get("energy_delivered", details.get("delivered_energy_kwh", 0))
        quantity = details.get("quantity", details.get("monthly_scm", details.get("monthly_kg", 0)))
        unit = details.get("unit", "")
        parts.append(
            f"{fuel_name}: {fmt_number(delivered, 2)} kWh, "
            f"{fmt_number(quantity, 3)} {unit}".strip()
        )
    return "<br>".join(parts)


def residential_environmental_grade(result: dict[str, Any], household: dict[str, Any]) -> str:
    return result.get("environmental_grade") or helper.get_environmental_grade(
        emissions_value(result),
        household_size=household["household_size"],
    )


def health_snapshot(result: dict[str, Any], kitchen: dict[str, Any]) -> dict[str, Any]:
    return helper.calculate_health_impact(copy.deepcopy(result), copy.deepcopy(kitchen))


def append_alternative_analysis(
    lines: list[str],
    alternatives: dict[str, Any],
    recommendations: list[tuple[str, float, dict[str, Any]]],
) -> None:
    if not alternatives:
        return

    lines.append("#### Alternative fuels")
    lines.append("")
    append_table(
        lines,
        ["Alternative fuel", "Monthly cost", "Annual CO2", "Health risk", "Health grade", "Env grade", "Cost/kWh"],
        [
            [
                fuel_name,
                fmt_money(data.get("monthly_cost", 0)),
                fmt_number(emissions_value(data), 2),
                fmt_number(data.get("health_risk_score", 0), 2),
                data.get("health_risk_category", ""),
                data.get("environmental_grade", ""),
                fmt_number(data.get("cost_per_kwh", 0), 3),
            ]
            for fuel_name, data in alternatives.items()
        ],
    )

    if recommendations:
        lines.append("")
        lines.append("Top 3 recommendation ranking:")
        lines.append("")
        append_table(
            lines,
            ["Rank", "Fuel", "Weighted score", "Monthly cost", "Annual CO2"],
            [
                [
                    index + 1,
                    recommendation[0],
                    fmt_number(recommendation[1], 2),
                    fmt_money(recommendation[2].get("monthly_cost", 0)),
                    fmt_number(emissions_value(recommendation[2]), 2),
                ]
                for index, recommendation in enumerate(recommendations[:3])
            ],
        )


def residential_dish_category_counts() -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in db_helper.get_all_dishes("residential"):
        category = row["category_name"]
        counts[category] = counts.get(category, 0) + 1
    return [{"category": category, "dish_count": count} for category, count in counts.items()]


def commercial_dish_category_counts() -> OrderedDict[str, dict[str, int]]:
    counts: OrderedDict[str, dict[str, int]] = OrderedDict()
    for institution_type in commercial_profiles().keys():
        counts[institution_type] = {}

    for row in db_helper.get_all_dishes("commercial"):
        institution_type = row["institution_type"]
        category = row["category_name"]
        if institution_type not in counts:
            counts[institution_type] = {}
        counts[institution_type][category] = counts[institution_type].get(category, 0) + 1
    return counts


def build_residential_consumption_variants(
    household: dict[str, Any],
    kitchen: dict[str, Any],
) -> dict[str, Any]:
    district = household["district"]
    lpg_price_row = db_helper.get_fuel_unit_price(district, "LPG", "Domestic") or {}
    domestic_subsidized = as_float(
        lpg_price_row.get("subsidized_unit_price")
        or lpg_price_row.get("unit_price")
        or 600
    )
    domestic_price_per_kg = domestic_subsidized / 14.2 if domestic_subsidized else 0

    lpg_variants = []
    for cylinder_size in (5.0, 14.2, 19.0):
        cylinder_price = round(domestic_price_per_kg * cylinder_size, 2) if domestic_price_per_kg else 0
        form = {
            "primary_fuel": "LPG",
            "district": district,
            "refill_days": "30",
            "cylinder_price": f"{cylinder_price:.2f}",
            "cylinder_size": f"{cylinder_size:g}",
        }
        result = residential_cooking.calculate_consumption_based(
            form,
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        )
        lpg_variants.append(
            {
                "primary_fuel": "LPG",
                "variant": f"{cylinder_size:g} kg cylinder preset",
                "formula_family": "LPG refill-days",
                "form": form,
                "result": result,
                "health": health_snapshot(result, kitchen),
            }
        )

    png_rate = as_float(db_helper.get_png_pricing(district="All", category="Domestic")["price_per_scm"])
    png_monthly_bill = 1800.0
    png_monthly_scm = png_monthly_bill / png_rate if png_rate else 0
    png_daily_scm = png_monthly_scm / 30 if png_monthly_scm else 0
    png_variants = []
    for variant, form in (
        (
            "Bill input",
            {"primary_fuel": "PNG", "png_input_method": "bill", "monthly_bill": f"{png_monthly_bill:.2f}"},
        ),
        (
            "Monthly SCM input",
            {"primary_fuel": "PNG", "png_input_method": "scm", "monthly_scm": f"{png_monthly_scm:.4f}"},
        ),
        (
            "Daily SCM input",
            {"primary_fuel": "PNG", "png_input_method": "daily", "daily_scm": f"{png_daily_scm:.4f}"},
        ),
    ):
        result = residential_cooking.calculate_consumption_based(
            form,
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        )
        png_variants.append(
            {
                "primary_fuel": "PNG",
                "variant": variant,
                "formula_family": f"PNG {form['png_input_method']}",
                "form": form,
                "result": result,
                "health": health_snapshot(result, kitchen),
            }
        )

    other_single_variants = []
    for primary_fuel, variant, form, formula_family in (
        (
            "Grid electricity",
            "Monthly kWh input",
            {"primary_fuel": "Grid electricity", "monthly_kwh_cooking": "85"},
            "Electricity units",
        ),
        (
            "Traditional Solid Biomass",
            "Monthly kg input",
            {
                "primary_fuel": "Traditional Solid Biomass",
                "monthly_kg": "75",
                "biomass_type": "Firewood",
            },
            "Biomass kg",
        ),
    ):
        result = residential_cooking.calculate_consumption_based(
            form,
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        )
        other_single_variants.append(
            {
                "primary_fuel": primary_fuel,
                "variant": variant,
                "formula_family": formula_family,
                "form": form,
                "result": result,
                "health": health_snapshot(result, kitchen),
            }
        )

    mixed_templates: OrderedDict[str, list[tuple[str, str]]] = OrderedDict(
        [
            ("LPG", [("mixed_use_lpg", "on"), ("mixed_refill_days", "60")]),
            ("PNG", [("mixed_use_png", "on"), ("mixed_monthly_bill_png", "900")]),
            ("Grid electricity", [("mixed_use_elec", "on"), ("mixed_monthly_kwh", "35")]),
            ("Traditional Solid Biomass", [("mixed_use_biomass", "on"), ("mixed_monthly_kg_biomass", "25")]),
        ]
    )
    mixed_rows = []
    for subset in non_empty_subsets(list(mixed_templates.keys())):
        form_pairs: list[tuple[str, str]] = [("primary_fuel", "Mixed usage"), ("district", district)]
        for fuel_name in subset:
            form_pairs.extend(mixed_templates[fuel_name])
        form = MultiDict(form_pairs)
        result = residential_cooking.calculate_consumption_based(
            form,
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        )
        mixed_rows.append(
            {
                "primary_fuel": "Mixed usage",
                "variant": mix_label(subset),
                "selected_fuels": subset,
                "formula_family": "Mixed fuel sum",
                "form": form,
                "result": result,
                "health": health_snapshot(result, kitchen),
            }
        )

    all_rows = lpg_variants + png_variants + other_single_variants + mixed_rows
    return {
        "lpg_variants": lpg_variants,
        "png_variants": png_variants,
        "other_single_variants": other_single_variants,
        "mixed_rows": mixed_rows,
        "all_rows": all_rows,
        "mixed_fuel_pool": list(mixed_templates.keys()),
        "png_rate": png_rate,
        "domestic_lpg_price_row": lpg_price_row,
    }


def build_commercial_consumption_variants(
    profiles: OrderedDict[str, dict[str, Any]],
) -> dict[str, Any]:
    png_rate = as_float(db_helper.get_png_pricing(district="Thiruvananthapuram", category="Commercial")["price_per_scm"])
    png_monthly_bill = 3500.0
    png_monthly_scm = png_monthly_bill / png_rate if png_rate else 0

    mixed_templates: OrderedDict[str, list[tuple[str, str]]] = OrderedDict(
        [
            ("LPG", [("mixed_use_lpg", "on"), ("mixed_commercial_cylinders", "3")]),
            ("PNG", [("mixed_use_png", "on"), ("mixed_monthly_bill_png", "12000")]),
            ("Grid electricity", [("mixed_use_elec", "on"), ("mixed_monthly_kwh", "450")]),
            ("Traditional Solid Biomass", [("mixed_use_biomass", "on"), ("mixed_monthly_kg_biomass", "120")]),
        ]
    )

    single_rows = []
    mixed_rows = []

    for _, profile in profiles.items():
        kitchen = commercial_kitchen(profile)
        base_variants = [
            (
                "LPG",
                "Domestic cylinders only",
                MultiDict(
                    [
                        ("primary_fuel", "LPG"),
                        ("lpg_types", "Domestic"),
                        ("domestic_cylinders", "4"),
                    ]
                ),
                "LPG domestic-only",
            ),
            (
                "LPG",
                "Commercial cylinders only",
                MultiDict(
                    [
                        ("primary_fuel", "LPG"),
                        ("lpg_types", "Commercial"),
                        ("commercial_cylinders", "4"),
                    ]
                ),
                "LPG commercial-only",
            ),
            (
                "LPG",
                "Domestic + Commercial cylinders",
                MultiDict(
                    [
                        ("primary_fuel", "LPG"),
                        ("lpg_types", "Domestic"),
                        ("lpg_types", "Commercial"),
                        ("domestic_cylinders", "1"),
                        ("commercial_cylinders", "4"),
                    ]
                ),
                "LPG dual-cylinder",
            ),
            (
                "PNG",
                "Bill input",
                MultiDict(
                    [
                        ("primary_fuel", "PNG"),
                        ("png_input_method", "bill"),
                        ("monthly_bill", f"{png_monthly_bill:.2f}"),
                    ]
                ),
                "PNG bill",
            ),
            (
                "PNG",
                "Monthly SCM input",
                MultiDict(
                    [
                        ("primary_fuel", "PNG"),
                        ("png_input_method", "scm"),
                        ("monthly_scm", f"{png_monthly_scm:.4f}"),
                    ]
                ),
                "PNG scm",
            ),
            (
                "Grid electricity",
                "Monthly kWh input",
                MultiDict([("primary_fuel", "Grid electricity"), ("monthly_kwh", "900")]),
                "Electricity units",
            ),
            (
                "Biogas",
                "Daily m3 + monthly OPEX",
                MultiDict(
                    [
                        ("primary_fuel", "Biogas"),
                        ("daily_biogas_m3", "12"),
                        ("biogas_monthly_cost", "5000"),
                    ]
                ),
                "Biogas m3",
            ),
            (
                "Traditional Solid Biomass",
                "Monthly kg input",
                MultiDict(
                    [
                        ("primary_fuel", "Traditional Solid Biomass"),
                        ("monthly_biomass_kg", "350"),
                        ("biomass_type", "Firewood"),
                    ]
                ),
                "Biomass kg",
            ),
        ]

        for primary_fuel, variant, form, formula_family in base_variants:
            result = commercial_cooking.calculate_consumption_based(
                form,
                copy.deepcopy(profile),
                copy.deepcopy(kitchen),
                None,
            )
            single_rows.append(
                {
                    "institution_type": profile["institution_type"],
                    "primary_fuel": primary_fuel,
                    "variant": variant,
                    "formula_family": formula_family,
                    "form": form,
                    "result": result,
                    "health": health_snapshot(result, kitchen),
                }
            )

        for subset in non_empty_subsets(list(mixed_templates.keys())):
            form_pairs: list[tuple[str, str]] = [("primary_fuel", "Mixed usage")]
            for fuel_name in subset:
                form_pairs.extend(mixed_templates[fuel_name])
            form = MultiDict(form_pairs)
            result = commercial_cooking.calculate_consumption_based(
                form,
                copy.deepcopy(profile),
                copy.deepcopy(kitchen),
                None,
            )
            mixed_rows.append(
                {
                    "institution_type": profile["institution_type"],
                    "primary_fuel": "Mixed usage",
                    "variant": mix_label(subset),
                    "selected_fuels": subset,
                    "formula_family": "Mixed fuel sum",
                    "form": form,
                    "result": result,
                    "health": health_snapshot(result, kitchen),
                }
            )

    return {
        "single_rows": single_rows,
        "mixed_rows": mixed_rows,
        "all_rows": single_rows + mixed_rows,
        "mixed_fuel_pool": list(mixed_templates.keys()),
        "png_rate": png_rate,
    }


def residential_dish_debug(
    household: dict[str, Any],
    selection_rows: list[dict[str, Any]],
    meal_types: dict[str, str],
) -> dict[str, Any]:
    dishes_df = pd.DataFrame(db_helper.get_all_dishes("residential"))
    if "dish_name" in dishes_df.columns and "Dishes" not in dishes_df.columns:
        dishes_df = dishes_df.rename(
            columns={
                "dish_name": "Dishes",
                "dish_name_ml": "Dishes_ml",
                "category_name": "Category",
            }
        )
    user_df = pd.DataFrame(selection_rows)
    merged = pd.merge(user_df, dishes_df, on="Dishes", how="left", suffixes=("_user", "_dish"))
    merged["Category"] = merged["Category_user"]
    energy_df = residential_cooking.monthly_calories(
        merged,
        household["household_size"],
        total_calories_per_person=2400,
        breakfast=meal_types["breakfast_type"],
        lunch=meal_types["lunch_type"],
        dinner=meal_types["dinner_type"],
    )

    household_efficiency = residential_cooking.get_household_size_factor(household["household_size"])
    base_wastage = as_float(db_helper.get_system_parameter("COOKING_WASTAGE_BASE", 1.15))
    min_wastage = as_float(db_helper.get_system_parameter("COOKING_WASTAGE_MIN", 1.05))
    wastage_factor = max(min_wastage, base_wastage - (0.05 * (household["household_size"] - 2) / 6))

    breakfast_dist = db_helper.get_meal_distribution(meal_types["breakfast_type"])
    lunch_dist = db_helper.get_meal_distribution(meal_types["lunch_type"])
    dinner_dist = db_helper.get_meal_distribution(meal_types["dinner_type"])
    snacks_dist = db_helper.get_meal_distribution("Normal")
    target_map = {
        "Breakfast": breakfast_dist.get("Breakfast", 0) * 2400 * household["household_size"] * 30,
        "Lunch": lunch_dist.get("Lunch", 0) * 2400 * household["household_size"] * 30,
        "Dinner": dinner_dist.get("Dinner", 0) * 2400 * household["household_size"] * 30,
        "Snacks": snacks_dist.get("Snacks", 0) * 2400 * household["household_size"] * 30,
    }

    categories = []
    for category in ("Breakfast", "Lunch", "Dinner", "Snacks"):
        mask = energy_df["Category"] == category
        if not mask.any():
            continue
        actual_calories = energy_df.loc[mask, "total_calories"].sum()
        scaling = target_map[category] / actual_calories if actual_calories > 0 else 0
        categories.append(
            {
                "category": category,
                "target_calories": target_map[category],
                "actual_calories": actual_calories,
                "scaling_factor": scaling,
                "monthly_energy_kwh": energy_df.loc[mask, "Final_Energy_Value"].sum(),
            }
        )

    return {"energy_df": energy_df, "categories": categories, "wastage_factor": wastage_factor, "household_efficiency": household_efficiency}


def commercial_dish_debug(
    institution: dict[str, Any],
    selection_rows: list[dict[str, Any]],
    meal_types: dict[str, str],
) -> dict[str, Any]:
    dishes_df = pd.DataFrame(db_helper.get_all_dishes("commercial"))
    dishes_df = dishes_df[dishes_df["institution_type"] == institution["institution_type"]].copy()
    if "dish_name" in dishes_df.columns and "Dishes" not in dishes_df.columns:
        dishes_df = dishes_df.rename(
            columns={
                "dish_name": "Dishes",
                "dish_name_ml": "Dishes_ml",
                "category_name": "Category",
            }
        )

    user_df = pd.DataFrame(selection_rows)
    merged = pd.merge(user_df, dishes_df, on="Dishes", how="left", suffixes=("_user", "_dish"))
    merged["Category"] = merged["Category_user"]
    energy_df = commercial_cooking.commercial_monthly_energy(
        merged,
        institution["servings_per_day"],
        institution["working_days"],
        institution["institution_type"],
        breakfast=meal_types["breakfast_type"],
        lunch=meal_types["lunch_type"],
        dinner=meal_types["dinner_type"],
    )

    serving_efficiency = commercial_cooking.get_serving_volume_efficiency(institution["servings_per_day"])
    wastage_factor = commercial_cooking.get_commercial_wastage_factor(
        institution["servings_per_day"], institution["institution_type"]
    )

    categories = []
    monthly_servings = institution["servings_per_day"] * institution["working_days"]
    for category in ("Breakfast", "Lunch", "Dinner", "Snacks"):
        mask = energy_df["Category"].str.lower() == category.lower()
        if not mask.any():
            continue
        if category == "Breakfast":
            intensity = meal_types["breakfast_type"]
        elif category == "Lunch":
            intensity = meal_types["lunch_type"]
        elif category == "Dinner":
            intensity = meal_types["dinner_type"]
        else:
            intensity = "Normal"
        calories_per_serving = commercial_cooking.get_institution_meal_calories(
            institution["institution_type"], category, intensity
        )
        target_calories_monthly = calories_per_serving * monthly_servings
        actual_per_serving = energy_df.loc[mask, "total_calories"].sum()
        actual_calories_monthly = actual_per_serving * monthly_servings
        scaling = target_calories_monthly / actual_calories_monthly if actual_calories_monthly > 0 else 0
        categories.append(
            {
                "category": category,
                "meal_intensity": intensity,
                "target_calories_monthly": target_calories_monthly,
                "actual_calories_per_serving": actual_per_serving,
                "actual_calories_monthly": actual_calories_monthly,
                "scaling_factor": scaling,
                "monthly_energy_kwh": energy_df.loc[mask, "Final_Energy_Value"].sum(),
            }
        )

    return {"energy_df": energy_df, "categories": categories, "serving_efficiency": serving_efficiency, "wastage_factor": wastage_factor}


def residential_examples() -> dict[str, Any]:
    household, kitchen = base_residential_profile()
    consumption_variants = build_residential_consumption_variants(household, kitchen)

    examples = OrderedDict()
    examples["LPG"] = {
        "form": {
            "primary_fuel": "LPG",
            "district": household["district"],
            "refill_days": "30",
            "cylinder_price": "600",
            "cylinder_size": "14.2",
        },
        "result": residential_cooking.calculate_consumption_based(
            {
                "primary_fuel": "LPG",
                "district": household["district"],
                "refill_days": "30",
                "cylinder_price": "600",
                "cylinder_size": "14.2",
            },
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        ),
    }
    examples["PNG"] = {
        "form": {
            "primary_fuel": "PNG",
            "png_input_method": "bill",
            "monthly_bill": "1800",
        },
        "result": residential_cooking.calculate_consumption_based(
            {
                "primary_fuel": "PNG",
                "png_input_method": "bill",
                "monthly_bill": "1800",
            },
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        ),
    }
    examples["Grid electricity"] = {
        "form": {
            "primary_fuel": "Grid electricity",
            "monthly_kwh_cooking": "85",
        },
        "result": residential_cooking.calculate_consumption_based(
            {
                "primary_fuel": "Grid electricity",
                "monthly_kwh_cooking": "85",
            },
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        ),
    }
    examples["Traditional Solid Biomass"] = {
        "form": {
            "primary_fuel": "Traditional Solid Biomass",
            "monthly_kg": "75",
            "biomass_type": "Firewood",
        },
        "result": residential_cooking.calculate_consumption_based(
            {
                "primary_fuel": "Traditional Solid Biomass",
                "monthly_kg": "75",
                "biomass_type": "Firewood",
            },
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        ),
    }
    examples["Mixed usage"] = {
        "form": {
            "primary_fuel": "Mixed usage",
            "mixed_use_lpg": "on",
            "mixed_refill_days": "60",
            "mixed_use_png": "on",
            "mixed_monthly_bill_png": "900",
            "mixed_use_elec": "on",
            "mixed_monthly_kwh": "35",
            "mixed_use_biomass": "on",
            "mixed_monthly_kg_biomass": "25",
        },
        "result": residential_cooking.calculate_consumption_based(
            {
                "primary_fuel": "Mixed usage",
                "district": household["district"],
                "mixed_use_lpg": "on",
                "mixed_refill_days": "60",
                "mixed_use_png": "on",
                "mixed_monthly_bill_png": "900",
                "mixed_use_elec": "on",
                "mixed_monthly_kwh": "35",
                "mixed_use_biomass": "on",
                "mixed_monthly_kg_biomass": "25",
            },
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            None,
        ),
    }

    for example in examples.values():
        example["alternatives"] = helper.calculate_alternatives(
            copy.deepcopy(example["result"]),
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
        )
        example["recommendations"] = helper.generate_recommendations(
            example["alternatives"],
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
            copy.deepcopy(example["result"]),
        )

    dish_picks = first_residential_dishes()
    fuel_cycle = {
        "Breakfast": "LPG",
        "Lunch": "PNG",
        "Dinner": "Grid electricity",
        "Snacks": "Traditional Solid Biomass",
    }
    dish_selection_rows = []
    dish_form_pairs: list[tuple[str, str]] = [
        ("calculation_method", "dish"),
        ("breakfast_type", "Normal"),
        ("lunch_type", "Heavy"),
        ("dinner_type", "Light"),
    ]
    for category, dish_row in dish_picks.items():
        if category not in fuel_cycle:
            continue
        fuel = fuel_cycle[category]
        dish_name = dish_row["dish_name"]
        dish_selection_rows.append({"Dishes": dish_name, "Category": category, "stoves": fuel})
        dish_form_pairs.append((f"{category.lower()}_dishes", dish_name))
        dish_form_pairs.append((f"{dish_name}_fuel", fuel))

    dish_meal_types = {"breakfast_type": "Normal", "lunch_type": "Heavy", "dinner_type": "Light"}
    dish_form = MultiDict(dish_form_pairs)
    dish_result = residential_cooking.calculate_dish_based(
        dish_form, copy.deepcopy(household), copy.deepcopy(kitchen), None, language="en"
    )
    dish_debug = residential_dish_debug(household, dish_selection_rows, dish_meal_types)
    dish_subset_examples = build_residential_dish_subset_examples(
        household,
        kitchen,
        dish_meal_types,
    )
    dish_analysis = {
        "alternatives": helper.calculate_alternatives(
            copy.deepcopy(dish_result),
            copy.deepcopy(household),
            copy.deepcopy(kitchen),
        ),
        "health": helper.calculate_health_impact(copy.deepcopy(dish_result), copy.deepcopy(kitchen)),
        "recommendations": [],
    }
    dish_analysis["recommendations"] = helper.generate_recommendations(
        dish_analysis["alternatives"],
        copy.deepcopy(household),
        copy.deepcopy(kitchen),
        copy.deepcopy(dish_result),
    )

    return {
        "household": household,
        "kitchen": kitchen,
        "consumption_examples": examples,
        "consumption_variants": consumption_variants,
        "dish_category_counts": residential_dish_category_counts(),
        "dish_selection_rows": dish_selection_rows,
        "dish_meal_types": dish_meal_types,
        "dish_result": dish_result,
        "dish_debug": dish_debug,
        "dish_subset_examples": dish_subset_examples,
        "dish_analysis": dish_analysis,
    }


def commercial_examples() -> dict[str, Any]:
    profiles = commercial_profiles()
    consumption_variants = build_commercial_consumption_variants(profiles)

    consumption_examples = OrderedDict()
    consumption_examples["School LPG"] = {
        "institution": profiles["School"],
        "kitchen": commercial_kitchen(profiles["School"]),
        "form": MultiDict(
            [
                ("primary_fuel", "LPG"),
                ("lpg_types", "Domestic"),
                ("lpg_types", "Commercial"),
                ("domestic_cylinders", "1"),
                ("commercial_cylinders", "4"),
            ]
        ),
    }
    consumption_examples["Anganwadi PNG"] = {
        "institution": profiles["Anganwadi"],
        "kitchen": commercial_kitchen(profiles["Anganwadi"]),
        "form": MultiDict(
            [
                ("primary_fuel", "PNG"),
                ("png_input_method", "bill"),
                ("monthly_bill", "3500"),
            ]
        ),
    }
    consumption_examples["Hotel Grid electricity"] = {
        "institution": profiles["Hotel"],
        "kitchen": commercial_kitchen(profiles["Hotel"]),
        "form": MultiDict(
            [
                ("primary_fuel", "Grid electricity"),
                ("monthly_kwh", "900"),
            ]
        ),
    }
    consumption_examples["Factory Biogas"] = {
        "institution": profiles["Factory"],
        "kitchen": commercial_kitchen(profiles["Factory"]),
        "form": MultiDict(
            [
                ("primary_fuel", "Biogas"),
                ("daily_biogas_m3", "12"),
                ("biogas_monthly_cost", "5000"),
            ]
        ),
    }
    consumption_examples["Community Kitchen Biomass"] = {
        "institution": profiles["Community Kitchen"],
        "kitchen": commercial_kitchen(profiles["Community Kitchen"]),
        "form": MultiDict(
            [
                ("primary_fuel", "Traditional Solid Biomass"),
                ("monthly_biomass_kg", "350"),
                ("biomass_type", "Firewood"),
            ]
        ),
    }
    consumption_examples["Hotel Mixed usage"] = {
        "institution": profiles["Hotel"],
        "kitchen": commercial_kitchen(profiles["Hotel"]),
        "form": MultiDict(
            [
                ("primary_fuel", "Mixed usage"),
                ("mixed_use_lpg", "on"),
                ("mixed_commercial_cylinders", "3"),
                ("mixed_use_png", "on"),
                ("mixed_monthly_bill_png", "12000"),
                ("mixed_use_elec", "on"),
                ("mixed_monthly_kwh", "450"),
                ("mixed_use_biomass", "on"),
                ("mixed_monthly_kg_biomass", "120"),
            ]
        ),
    }

    for example in consumption_examples.values():
        example["result"] = commercial_cooking.calculate_consumption_based(
            example["form"],
            copy.deepcopy(example["institution"]),
            copy.deepcopy(example["kitchen"]),
            None,
        )
        example["alternatives"] = helper.calculate_commercial_alternatives(
            copy.deepcopy(example["result"]),
            copy.deepcopy(example["institution"]),
            copy.deepcopy(example["kitchen"]),
        )
        example["recommendations"] = helper.generate_recommendations(
            example["alternatives"],
            copy.deepcopy(example["institution"]),
            copy.deepcopy(example["kitchen"]),
            copy.deepcopy(example["result"]),
        )

    dish_examples = OrderedDict()
    dish_subset_examples = OrderedDict()
    fuel_rotation = ["LPG", "PNG", "Grid electricity", "Traditional Solid Biomass"]
    for name, profile in profiles.items():
        picked = first_commercial_dishes(name)
        selection_rows = []
        form_pairs: list[tuple[str, str]] = [
            ("calculation_method", "dish"),
            ("servings_per_day", str(profile["servings_per_day"])),
            ("working_days_per_month", str(profile["working_days"])),
            ("breakfast_type", "Normal"),
            ("lunch_type", "Heavy"),
            ("dinner_type", "Light"),
        ]
        fuel_index = 0
        for category in ("Breakfast", "Lunch", "Dinner", "Snacks"):
            dish_row = picked.get(category)
            if not dish_row:
                continue
            fuel = fuel_rotation[fuel_index % len(fuel_rotation)]
            fuel_index += 1
            dish_name = dish_row["dish_name"]
            selection_rows.append({"Dishes": dish_name, "Category": category, "stoves": fuel})
            form_pairs.append((f"{category.lower()}_dishes", dish_name))
            form_pairs.append((f"{dish_name}_fuel", fuel))

        meal_types = {"breakfast_type": "Normal", "lunch_type": "Heavy", "dinner_type": "Light"}
        form = MultiDict(form_pairs)
        kitchen = commercial_kitchen(profile)
        result = commercial_cooking.calculate_dish_based(
            form,
            copy.deepcopy(profile),
            copy.deepcopy(kitchen),
            None,
        )
        debug = commercial_dish_debug(profile, selection_rows, meal_types)
        dish_examples[name] = {
            "institution": profile,
            "kitchen": kitchen,
            "selection_rows": selection_rows,
            "meal_types": meal_types,
            "result": result,
            "debug": debug,
        }
        dish_example_alternatives = helper.calculate_commercial_alternatives(
            copy.deepcopy(result),
            copy.deepcopy(profile),
            copy.deepcopy(kitchen),
        )
        dish_examples[name]["alternatives"] = dish_example_alternatives
        dish_examples[name]["recommendations"] = helper.generate_recommendations(
            dish_example_alternatives,
            copy.deepcopy(profile),
            copy.deepcopy(kitchen),
            copy.deepcopy(result),
        )
        dish_subset_examples[name] = build_commercial_dish_subset_examples(
            profile,
            kitchen,
            meal_types,
        )

    hotel_analysis_source = dish_examples["Hotel"]
    hotel_alternatives = copy.deepcopy(hotel_analysis_source["alternatives"])
    hotel_analysis = {
        "alternatives": hotel_alternatives,
        "health": helper.calculate_health_impact(
            copy.deepcopy(hotel_analysis_source["result"]),
            copy.deepcopy(hotel_analysis_source["kitchen"]),
        ),
        "recommendations": helper.generate_recommendations(
            hotel_alternatives,
            copy.deepcopy(hotel_analysis_source["institution"]),
            copy.deepcopy(hotel_analysis_source["kitchen"]),
            copy.deepcopy(hotel_analysis_source["result"]),
        ),
    }

    return {
        "profiles": profiles,
        "consumption_examples": consumption_examples,
        "consumption_variants": consumption_variants,
        "dish_examples": dish_examples,
        "dish_subset_examples": dish_subset_examples,
        "dish_category_counts": commercial_dish_category_counts(),
        "hotel_analysis": hotel_analysis,
    }


def append_intro(lines: list[str], reference: dict[str, Any]) -> None:
    lines.append("# Technical Debug Guide")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("This document is generated from the live SQLite reference data in `cooking_webapp.db` and the same Python calculation functions used by the Flask app. It is written for debugging flow, formula, and data inconsistencies.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("- Residential user flow and calculations")
    lines.append("- Commercial user flow and calculations")
    lines.append("- Flask route flow and Node migration parity points")
    lines.append("- Real examples using DB values and reproducible form inputs")
    lines.append("- Fallback and alias watchlist for parameters that can change outputs")
    lines.append("")
    lines.append("## Route And State Flow")
    lines.append("")
    append_table(
        lines,
        ["Concern", "Flask flow", "Node migration parity"],
        [
            [
                "Residential start",
                "`/household_profile` -> `POST /submit_household` -> `/kitchen_profile` -> `POST /submit_kitchen` -> `/energy_calculation`",
                "Same routes in `node-migration/src/routes/web.js`; controller methods live in `node-migration/src/controllers/web-controller.js`.",
            ],
            [
                "Residential calculation",
                "`POST /calculate_consumption` stores `session['energy_data']` then `/analysis` computes alternatives, health, and recommendations.",
                "`calculateConsumption()` stores `req.session.energy_data` and immediately calls `finalizeResidentialAnalysis()` before redirecting to `/analysis`.",
            ],
            [
                "Commercial start",
                "`/commercial_selection` -> `POST /commercial_institution_profile` -> `/commercial/kitchen-profile` -> `POST /commercial/submit_kitchen` -> `/commercial_energy_calculation`",
                "Same route shape in the Node router and controller.",
            ],
            [
                "Commercial calculation",
                "`POST /commercial_energy_calculation` stores `session['energy_data']`; `/commercial_analysis` computes alternatives, health, recommendations.",
                "`commercialEnergyCalculation()` calculates and immediately calls `finalizeCommercialAnalysis()`.",
            ],
            [
                "Key session state",
                "`household_data`, `institution_data`, `kitchen_data`, `energy_data`, `residential_analysis_result`, `commercial_analysis_result`, `analysis_result`",
                "Equivalent Express session keys are used so templates and APIs can stay compatible.",
            ],
        ],
    )

    lines.append("## Live Reference Snapshot")
    lines.append("")
    append_table(
        lines,
        ["Fuel", "Thermal efficiency", "CO2 factor (kg/kWh)", "PM2.5 factor"],
        [
            [
                row["fuel_name"],
                fmt_percent(get_reference_efficiency(reference, row["fuel_name"]) * 100),
                fmt_number(row.get("co2_factor") or 0, 3),
                fmt_number(row.get("pm25_factor") or 0, 3),
            ]
            for row in reference["fuel_rows"]
        ],
    )

    append_table(
        lines,
        ["Requested parameter", "Resolved DB name", "Resolved value", "Source"],
        [
            [row["requested"], row["resolved_name"], row["resolved_value"], row["source"]]
            for row in reference["watched_params"]
        ],
    )

    append_table(
        lines,
        ["Scenario type", "Scenario name", "Combined factor", "Risk category"],
        [
            [row["scenario_type"], row["scenario_name"], fmt_number(row["combined_factor"], 2), row["health_risk_category"]]
            for row in reference["scenario_rows"]
        ],
    )

    append_table(
        lines,
        ["Group type", "Range", "Efficiency factor"],
        [
            [row["group_type"], f"{row['size_min']}-{row['size_max']}", fmt_number(row["efficiency_factor"], 2)]
            for row in reference["group_rows"]
        ],
    )

    meal_rows = [
        [
            row["institution_type"],
            row["meal_type"],
            row["calories_normal"],
            row["calories_heavy"],
            row["calories_light"],
        ]
        for row in reference["meal_rows"]
    ]
    append_table(lines, ["Institution", "Meal", "Normal", "Heavy", "Light"], meal_rows)

    append_table(
        lines,
        ["District snapshot", "Fuel", "Pricing category", "Unit price", "Subsidized unit price", "Unit"],
        [
            [
                row["district_name"],
                row["fuel_name"],
                row["pricing_category"],
                fmt_number(row["unit_price"], 2),
                fmt_number(row["subsidized_unit_price"], 2),
                row["unit_name"],
            ]
            for row in reference["pricing_rows"]
        ],
    )

    append_table(
        lines,
        ["Intensity", "Meal", "Energy percent"],
        [
            [row["intensity"], row["meal_type"], f"{row['energy_percent']}%"]
            for row in reference["meal_distribution_rows"]
        ],
    )

    append_table(
        lines,
        ["Area", "Stove type", "Fuel", "Thermal efficiency"],
        [
            [row["area_type"], row["stove_type"], row["fuel_name"], fmt_percent(as_float(row["efficiency"]) * 100)]
            for row in reference["thermal_rows"]
        ],
    )

    append_table(
        lines,
        ["Grade", "CO2/serving kg", "CO2/member/day kg", "Annual/member kg", "Label"],
        [
            [
                row["grade_letter"],
                row["co2_per_serving_kg"],
                row["co2_per_member_daily_kg"],
                row["annual_per_member_kg"],
                row["label"],
            ]
            for row in reference["grade_rows"]
        ],
    )

    lines.append("## Common Calculation Formulas")
    lines.append("")
    lines.append("Shared residential and commercial helper formulas:")
    lines.append("")
    lines.append("1. `basic_calories = (calories_per_100g x portion_g) / 100`")
    lines.append("2. `annual_co2 = daily_energy_kwh x annual_days x emission_factor`")
    lines.append("3. Residential `annual_days = 365`; commercial `annual_days = working_days_per_month x 12`")
    lines.append("4. `pm25_peak = base_pm25 x kitchen_scenario_combined_factor`")
    lines.append("5. `health_risk_score = pm25_score + sensitive_penalty + duration_penalty`, except near-zero PM2.5 cases where penalties are suppressed")
    lines.append("6. `energy_required = useful_energy / efficiency`")
    lines.append("7. `monthly_cost = energy_required x cost_per_kwh` for standardized fuel comparisons")
    lines.append("8. Residential dish-based `final_energy = dish_energy x scaling_factor x household_size_efficiency x wastage_factor`")
    lines.append("9. Commercial dish-based `final_energy = dish_energy x scaling_factor x serving_volume_efficiency x wastage_factor x monthly_servings`")
    lines.append("10. `environmental_grade` is read from the DB range table, not hardcoded in code")
    lines.append("")


def append_residential(lines: list[str], reference: dict[str, Any], payload: dict[str, Any]) -> None:
    household = payload["household"]
    kitchen = payload["kitchen"]
    consumption_variants = payload["consumption_variants"]
    dish_subset_examples = payload["dish_subset_examples"]
    dish_fuel_pool = dish_subset_examples["fuel_pool"]
    base_dishes = dish_subset_examples["base_dishes"]
    lpg_eff = get_reference_efficiency(reference, "LPG")
    png_eff = get_reference_efficiency(reference, "PNG")
    grid_eff = get_reference_efficiency(reference, "Grid electricity")
    biomass_eff = get_reference_efficiency(reference, "Traditional Solid Biomass")
    lines.append("## Residential")
    lines.append("")
    lines.append("### Residential Base Inputs Used In This Guide")
    lines.append("")
    append_table(
        lines,
        ["Input", "Value"],
        [
            ["district", household["district"]],
            ["area_type", household["area_type"]],
            ["household_size", household["household_size"]],
            ["monthly_income", household["monthly_income"]],
            ["lpg_subsidy", household["lpg_subsidy"]],
            ["electricity_tariff", household["electricity_tariff"]],
            ["loan_interest_rate", household["loan_interest_rate"]],
            ["loan_tenure", household["loan_tenure"]],
            ["main_priority", household["main_priority"]],
            ["solar_willingness", household["solar_willingness"]],
            ["roof_area_available", kitchen["roof_area_available"]],
            ["kitchen_scenario", kitchen["kitchen_scenario"]],
            ["cooking_hours_daily", kitchen["cooking_hours_daily"]],
            ["sensitive_members", kitchen["sensitive_members"]],
        ],
    )

    lines.append("### Residential Combination Inventory")
    lines.append("")
    append_table(
        lines,
        ["Step", "Allowed combinations", "Count", "Code path"],
        [
            [
                "Consumption-based primary fuel",
                "LPG, PNG, Grid electricity, Traditional Solid Biomass, Mixed usage",
                "5",
                "`residential_cooking.calculate_consumption_based()`",
            ],
            [
                "Residential LPG preset sizes",
                "5 kg, 14.2 kg, 19 kg",
                "3",
                "Same LPG refill-days branch; only `cylinder_size` and user-entered `cylinder_price` change.",
            ],
            [
                "Residential PNG input methods",
                "bill, scm, daily",
                "3",
                "All resolve to monthly SCM before applying calorific value and efficiency.",
            ],
            [
                "Residential mixed usage toggles",
                "LPG, PNG, Grid electricity, Traditional Solid Biomass",
                str((2 ** len(consumption_variants["mixed_fuel_pool"])) - 1),
                "Non-empty subsets of the 4 mixed-mode fuel toggles.",
            ],
            [
                "Dish-based selectable fuels",
                mix_label(dish_fuel_pool),
                str((2 ** len(dish_fuel_pool)) - 1),
                "`current_fuel_mix` UI pool excludes `Solar + BESS`.",
            ],
            [
                "Dish assignment permutations",
                f"{len(base_dishes)} canonical dishes x selected fuel subset",
                f"{total_assignment_patterns(len(dish_fuel_pool), len(base_dishes)):,}",
                "Backend result depends on per-dish `dish_name_fuel` assignments, not on `current_fuel_mix` alone.",
            ],
        ],
    )

    append_table(
        lines,
        ["Residential dish category", "Dish count in DB"],
        [[row["category"], row["dish_count"]] for row in payload["dish_category_counts"]],
    )

    append_table(
        lines,
        ["Formula family", "Formula / behavior"],
        [
            [
                "LPG refill-days",
                f"`energy_per_cylinder = cylinder_size_kg x LPG_CALORIFIC_VALUE`; `daily_energy = energy_per_cylinder / refill_days`; `monthly_useful = daily_energy x 30 x {fmt_number(lpg_eff, 2)}`",
            ],
            [
                "PNG",
                f"`bill/scm/daily -> monthly_scm`; `monthly_gross = monthly_scm x PNG_CALORIFIC_VALUE`; `monthly_useful = monthly_gross x {fmt_number(png_eff, 2)}`",
            ],
            [
                "Grid electricity",
                f"`monthly_useful = monthly_kwh_cooking x {fmt_number(grid_eff, 2)}`; `monthly_cost = monthly_kwh_cooking x tariff`",
            ],
            [
                "Traditional biomass",
                f"`monthly_gross = monthly_kg x BIOMASS_ENERGY_CONTENT`; `monthly_useful = monthly_gross x {fmt_number(biomass_eff, 2)}`",
            ],
            [
                "Mixed usage",
                "Run each selected single-fuel branch independently, then sum `monthly_energy_kwh`, `monthly_cost`, and `annual_emissions`.",
            ],
            [
                "Dish-based",
                "`Final_Energy_Value = dish_energy x scaling_factor x household_size_efficiency x wastage_factor`; per-fuel totals then use `calculate_fuel_emissions_and_costs()`.",
            ],
        ],
    )

    lines.append("### Residential Consumption Combination Matrix (All UI Branches)")
    lines.append("")
    append_table(
        lines,
        ["Primary fuel", "Variant", "Example form inputs", "Fuel breakdown", "Monthly energy", "Monthly cost", "Annual CO2", "Health", "Env grade"],
        [
            [
                row["primary_fuel"],
                row["variant"],
                form_input_text(row["form"]),
                fuel_breakdown_summary(row["result"]),
                fmt_number(row["result"]["monthly_energy_kwh"]),
                fmt_money(row["result"]["monthly_cost"]),
                fmt_number(row["result"]["annual_emissions"]),
                f"{fmt_number(row['health']['health_risk_score'])} ({row['health']['health_risk_category']})",
                residential_environmental_grade(row["result"], household),
            ]
            for row in consumption_variants["all_rows"]
        ],
    )

    lines.append("### Residential Consumption-Based Worked Examples")
    lines.append("")
    for name, example in payload["consumption_examples"].items():
        result = example["result"]
        lines.append(f"#### {name}")
        lines.append("")
        append_table(lines, ["Form input", "Value"], [[k, v] for k, v in example["form"].items()])

        if name == "LPG":
            refill_days = as_float(example["form"]["refill_days"])
            cylinder_weight = as_float(example["form"]["cylinder_size"])
            cylinder_price = as_float(example["form"]["cylinder_price"])
            energy_per_cylinder = cylinder_weight * as_float(helper.LPG_CALORIFIC_VALUE)
            daily_energy = energy_per_cylinder / refill_days
            monthly_gross = daily_energy * 30
            efficiency = lpg_eff
            cylinders_per_month = 30 / refill_days
            lines.append("Step-by-step:")
            lines.append(f"1. `energy_per_cylinder = {fmt_number(cylinder_weight)} x {fmt_number(helper.LPG_CALORIFIC_VALUE)} = {fmt_number(energy_per_cylinder)} kWh`")
            lines.append(f"2. `daily_energy = {fmt_number(energy_per_cylinder)} / {fmt_number(refill_days)} = {fmt_number(daily_energy)} kWh/day`")
            lines.append(f"3. `monthly_useful_energy = ({fmt_number(daily_energy)} x 30) x {fmt_number(efficiency, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh/month`")
            lines.append(f"4. `monthly_cost = {fmt_number(cylinders_per_month)} x {fmt_number(cylinder_price)} = {fmt_money(result['monthly_cost'])}`")
            lines.append(f"5. `annual_co2 = {fmt_number(daily_energy)} x 365 x {fmt_number(helper.EMISSION_FACTORS['LPG'], 3)} = {fmt_number(result['annual_emissions'])} kg/year`")
        elif name == "PNG":
            png_rate = as_float(db_helper.get_png_pricing(district="All", category="Domestic")["price_per_scm"])
            png_data = helper.calculate_png_consumption_from_bill(as_float(example["form"]["monthly_bill"]), rate_per_scm=png_rate)
            efficiency = png_eff
            lines.append("Step-by-step:")
            lines.append(f"1. User enters monthly bill `{example['form']['monthly_bill']}`. Code reverse-solves monthly SCM using `calculate_png_consumption_from_bill()`.")
            lines.append(f"2. Solved `monthly_scm = {fmt_number(png_data['monthly_scm_consumption'], 3)} SCM` at `rate_per_scm = {fmt_number(png_rate, 2)}`.")
            lines.append(f"3. `monthly_gross_energy = {fmt_number(png_data['monthly_scm_consumption'], 3)} x {fmt_number(helper.PNG_CALORIFIC_VALUE)} = {fmt_number(png_data['monthly_energy_kwh'])} kWh`")
            lines.append(f"4. `monthly_useful_energy = {fmt_number(png_data['monthly_energy_kwh'])} x {fmt_number(efficiency, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
            lines.append(f"5. `annual_co2 = {fmt_number(png_data['daily_energy_kwh'])} x 365 x {fmt_number(helper.EMISSION_FACTORS['PNG'], 3)} = {fmt_number(result['annual_emissions'])} kg/year`")
            lines.append("6. Current DB has no PNG fixed charge or meter rent row, so both are falling back to `0` in this example.")
        elif name == "Grid electricity":
            monthly_kwh = as_float(example["form"]["monthly_kwh_cooking"])
            efficiency = grid_eff
            lines.append("Step-by-step:")
            lines.append(f"1. `monthly_useful_energy = {fmt_number(monthly_kwh)} x {fmt_number(efficiency, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
            lines.append(f"2. `monthly_cost = {fmt_number(monthly_kwh)} x {fmt_number(household['electricity_tariff'])} = {fmt_money(result['monthly_cost'])}`")
            lines.append(f"3. `annual_co2 = ({fmt_number(monthly_kwh)} / 30) x 365 x {fmt_number(helper.EMISSION_FACTORS['Grid electricity'], 3)} = {fmt_number(result['annual_emissions'])} kg/year`")
        elif name == "Traditional Solid Biomass":
            monthly_kg = as_float(example["form"]["monthly_kg"])
            biomass_energy = as_float(db_helper.get_system_parameter("BIOMASS_ENERGY_CONTENT", 4.5))
            biomass_cost = as_float(db_helper.get_system_parameter("BIOMASS_DEFAULT_COST", 5.0))
            efficiency = biomass_eff
            gross_energy = monthly_kg * biomass_energy
            lines.append("Step-by-step:")
            lines.append(f"1. `monthly_gross_energy = {fmt_number(monthly_kg)} x {fmt_number(biomass_energy)} = {fmt_number(gross_energy)} kWh`")
            lines.append(f"2. `monthly_useful_energy = {fmt_number(gross_energy)} x {fmt_number(efficiency, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
            lines.append(f"3. `monthly_cost = {fmt_number(monthly_kg)} x {fmt_number(biomass_cost)} = {fmt_money(result['monthly_cost'])}`")
            lines.append(f"4. `annual_co2 = ({fmt_number(gross_energy)} / 30) x 365 x {fmt_number(helper.EMISSION_FACTORS['Traditional Solid Biomass'], 3)} = {fmt_number(result['annual_emissions'])} kg/year`")
            lines.append(f"5. Thermal efficiency for biomass is taken from the DB-backed default-efficiency map in this example, which resolves `Traditional Solid Biomass` to `{fmt_number(efficiency, 2)}`.")
        else:
            lines.append("Fuel-by-fuel subtotal from the mixed example:")
            lines.append("")
            mixed_rows = []
            for fuel_name, fuel_data in result["fuel_details"].items():
                if not isinstance(fuel_data, dict):
                    continue
                mixed_rows.append(
                    [
                        fuel_name,
                        fmt_number(fuel_data.get("quantity", 0), 3),
                        fuel_data.get("unit", ""),
                        fmt_number(fuel_data.get("energy_delivered", 0), 3),
                        fmt_money(fuel_data.get("monthly_cost", 0)),
                        fmt_number(fuel_data.get("annual_emissions", 0), 2),
                    ]
                )
            append_table(lines, ["Fuel", "Quantity", "Unit", "Useful kWh/month", "Monthly cost", "Annual CO2"], mixed_rows)
            lines.append(f"Total monthly energy = {fmt_number(result['monthly_energy_kwh'])} kWh")
            lines.append(f"Total monthly cost = {fmt_money(result['monthly_cost'])}")
            lines.append(f"Total annual CO2 = {fmt_number(result['annual_emissions'])} kg/year")
        lines.append("")
        append_table(
            lines,
            ["Output field", "Value"],
            [
                ["monthly_energy_kwh", fmt_number(result["monthly_energy_kwh"])],
                ["monthly_cost", fmt_money(result["monthly_cost"])],
                ["annual_emissions", fmt_number(result["annual_emissions"])],
                ["overall_thermal_efficiency", fmt_percent(result.get("overall_thermal_efficiency", 0))],
            ],
        )
        append_alternative_analysis(lines, example.get("alternatives", {}), example.get("recommendations", []))

    lines.append("### Residential Dish Combination Inventory")
    lines.append("")
    append_table(
        lines,
        ["Canonical residential dish", "Category"],
        [[row["dish_name"], row["category_name"]] for row in base_dishes],
    )
    append_table(
        lines,
        ["Subset size", "Number of fuel subsets", f"Assignments per subset for {len(base_dishes)} dishes", "Total assignment patterns"],
        [
            [
                subset_size,
                len(list(combinations(dish_fuel_pool, subset_size))),
                assignment_count_for_subset(subset_size, len(base_dishes)),
                len(list(combinations(dish_fuel_pool, subset_size)))
                * assignment_count_for_subset(subset_size, len(base_dishes)),
            ]
            for subset_size in range(1, len(dish_fuel_pool) + 1)
        ],
    )
    lines.append("`current_fuel_mix` is a UI constraint only. The backend reads the actual `dish_name_fuel` assignment for each selected dish, so two submissions with the same checked mix can still produce different results if dish-to-fuel assignments differ.")
    lines.append("")
    lines.append("### Residential Dish Fuel-Subset Matrix (All 31 UI Fuel Mixes)")
    lines.append("")
    append_table(
        lines,
        ["Fuel mix", "Assigned dishes", "Selected fuels", "Dish count", "Theoretical assignments", "Monthly energy", "Monthly cost", "Annual CO2", "Health", "Env grade"],
        [
            [
                mix_label(row["fuel_mix"]),
                "<br>".join(row["assignment"]),
                row["selected_fuels"],
                row["dish_count"],
                row["assignment_count"],
                fmt_number(row["result"]["monthly_energy_kwh"]),
                fmt_money(row["result"]["monthly_cost"]),
                fmt_number(row["result"]["annual_emissions"]),
                f"{fmt_number((health := health_snapshot(row['result'], kitchen))['health_risk_score'])} ({health['health_risk_category']})",
                row["result"].get("environmental_grade", ""),
            ]
            for row in dish_subset_examples["subset_rows"]
        ],
    )

    lines.append("### Residential Dish-Based Worked Example")
    lines.append("")
    append_table(
        lines,
        ["Selected dish", "Category", "Assigned fuel"],
        [[row["Dishes"], row["Category"], row["stoves"]] for row in payload["dish_selection_rows"]],
    )
    append_table(lines, ["Meal intensity", "Value"], [[k, v] for k, v in payload["dish_meal_types"].items()])

    lines.append("Category scaling from `monthly_calories()`:")
    lines.append("")
    append_table(
        lines,
        ["Category", "Target calories/month", "Selected dish calories", "Scaling factor", "Useful energy/month"],
        [
            [
                row["category"],
                fmt_number(row["target_calories"], 0),
                fmt_number(row["actual_calories"], 2),
                fmt_number(row["scaling_factor"], 4),
                fmt_number(row["monthly_energy_kwh"], 3),
            ]
            for row in payload["dish_debug"]["categories"]
        ],
    )

    lines.append(f"Household size efficiency = {fmt_number(payload['dish_debug']['household_efficiency'], 2)}")
    lines.append(f"Wastage factor = {fmt_number(payload['dish_debug']['wastage_factor'], 3)}")
    lines.append("")
    append_table(
        lines,
        ["Dish", "Category", "Fuel", "Portion g", "Calories/100g", "Dish calories", "Base dish energy", "Final useful energy"],
        [
            [
                row["Dishes"],
                row["Category"],
                row["stoves"],
                fmt_number(row.get("minimum_portion_g", 0), 0),
                fmt_number(row.get("calories_per_100g", 0), 2),
                fmt_number(row.get("total_calories", 0), 2),
                fmt_number(row.get("energy_to_cook_kwh", 0), 4),
                fmt_number(row.get("Final_Energy_Value", 0), 4),
            ]
            for _, row in payload["dish_debug"]["energy_df"].iterrows()
        ],
    )

    append_table(
        lines,
        ["Fuel", "Useful kWh/month", "Energy required", "Monthly cost", "Annual CO2", "Cost per kWh"],
        [
            [
                fuel_name,
                fmt_number(details["energy_delivered"], 3),
                fmt_number(details["energy_required"], 3),
                fmt_money(details["monthly_cost"]),
                fmt_number(details["annual_emissions"], 2),
                fmt_number(details["cost_per_kwh"], 3),
            ]
            for fuel_name, details in payload["dish_result"]["fuel_details"]["fuel_breakdown"].items()
        ],
    )

    append_table(
        lines,
        ["Dish-based output field", "Value"],
        [
            ["monthly_energy_kwh", fmt_number(payload["dish_result"]["monthly_energy_kwh"])],
            ["monthly_cost", fmt_money(payload["dish_result"]["monthly_cost"])],
            ["annual_emissions", fmt_number(payload["dish_result"]["annual_emissions"])],
            ["overall_thermal_efficiency", fmt_percent(payload["dish_result"]["overall_thermal_efficiency"])],
            ["environmental_grade", payload["dish_result"].get("environmental_grade", "")],
        ],
    )

    lines.append("### Residential Analysis Example Based On The Dish Mix")
    lines.append("")
    append_table(
        lines,
        ["Current health metric", "Value"],
        [
            ["pm25_peak", fmt_number(payload["dish_analysis"]["health"]["pm25_peak"], 3)],
            ["health_risk_score", fmt_number(payload["dish_analysis"]["health"]["health_risk_score"], 2)],
            ["health_risk_category", payload["dish_analysis"]["health"]["health_risk_category"]],
        ],
    )

    append_table(
        lines,
        ["Alternative fuel", "Monthly cost", "Annual CO2", "Health risk", "Env grade"],
        [
            [
                fuel_name,
                fmt_money(data.get("monthly_cost", 0)),
                fmt_number(emissions_value(data), 2),
                fmt_number(data.get("health_risk_score", 0), 2),
                data.get("environmental_grade", ""),
            ]
            for fuel_name, data in payload["dish_analysis"]["alternatives"].items()
        ],
    )

    append_table(
        lines,
        ["Rank", "Fuel", "Weighted score", "Monthly cost", "Annual CO2"],
        [
            [
                index + 1,
                recommendation[0],
                fmt_number(recommendation[1], 2),
                fmt_money(recommendation[2].get("monthly_cost", 0)),
                fmt_number(emissions_value(recommendation[2]), 2),
            ]
            for index, recommendation in enumerate(payload["dish_analysis"]["recommendations"])
        ],
    )


def append_commercial(lines: list[str], reference: dict[str, Any], payload: dict[str, Any]) -> None:
    lpg_eff = get_reference_efficiency(reference, "LPG")
    png_eff = get_reference_efficiency(reference, "PNG")
    grid_eff = get_reference_efficiency(reference, "Grid electricity")
    biogas_eff = get_reference_efficiency(reference, "Biogas")
    biomass_eff = get_reference_efficiency(reference, "Traditional Solid Biomass")
    consumption_variants = payload["consumption_variants"]
    dish_subset_examples = payload["dish_subset_examples"]
    lines.append("## Commercial")
    lines.append("")
    lines.append("### Commercial Base Institution Inputs Used In This Guide")
    lines.append("")
    append_table(
        lines,
        ["Institution", "Servings/day", "Working days/month", "District", "Tariff", "Roof area"],
        [
            [
                profile["institution_type"],
                profile["servings_per_day"],
                profile["working_days"],
                profile["district"],
                fmt_number(profile["electricity_tariff"], 2),
                profile["available_roof_area"],
            ]
            for profile in payload["profiles"].values()
        ],
    )

    lines.append("### Commercial Combination Inventory")
    lines.append("")
    append_table(
        lines,
        ["Step", "Allowed combinations", "Count", "Code path"],
        [
            [
                "Institution type",
                ", ".join(payload["profiles"].keys()),
                str(len(payload["profiles"])),
                "User picks institution before kitchen and energy forms.",
            ],
            [
                "Consumption single-fuel / submethod branches",
                "LPG domestic-only, LPG commercial-only, LPG dual-cylinder, PNG bill, PNG scm, Grid electricity, Biogas, Traditional Solid Biomass",
                "8 per institution",
                "`commercial_cooking.calculate_consumption_based()`",
            ],
            [
                "Commercial mixed usage toggles",
                "LPG, PNG, Grid electricity, Traditional Solid Biomass",
                str((2 ** len(consumption_variants["mixed_fuel_pool"])) - 1),
                "Non-empty subsets of the 4 mixed-mode fuel toggles.",
            ],
            [
                "Dish-based selectable fuels",
                mix_label(next(iter(dish_subset_examples.values()))["fuel_pool"]),
                str((2 ** len(next(iter(dish_subset_examples.values()))["fuel_pool"])) - 1),
                "`current_fuel_mix` UI pool excludes `Solar + BESS` here too.",
            ],
            [
                "Dish assignment engine",
                "Per-dish `dish_name_fuel` assignments after institution-specific dish selection",
                "Varies by institution dish count",
                "`commercial_cooking.calculate_dish_based()`",
            ],
        ],
    )

    append_table(
        lines,
        ["Institution", "Breakfast dishes", "Lunch dishes", "Dinner dishes", "Snacks dishes", "Other categories"],
        [
            [
                institution,
                counts.get("Breakfast", 0),
                counts.get("Lunch", 0),
                counts.get("Dinner", 0),
                counts.get("Snacks", 0),
                sum(count for category, count in counts.items() if category not in ("Breakfast", "Lunch", "Dinner", "Snacks")),
            ]
            for institution, counts in payload["dish_category_counts"].items()
        ],
    )

    append_table(
        lines,
        ["Formula family", "Formula / behavior"],
        [
            [
                "LPG dual-cylinder",
                f"`gross_energy = (domestic_cyl x 14.2 + commercial_cyl x 19.0) x LPG_CALORIFIC_VALUE`; `delivered = gross_energy x {fmt_number(lpg_eff, 2)}`",
            ],
            [
                "PNG",
                f"`bill/scm -> monthly_scm`; `monthly_gross = monthly_scm x PNG_CALORIFIC_VALUE`; `monthly_useful = monthly_gross x {fmt_number(png_eff, 2)}`",
            ],
            [
                "Grid electricity",
                f"`monthly_useful = monthly_kwh x {fmt_number(grid_eff, 2)}`; annual CO2 uses commercial `working_days x 12` annualization.",
            ],
            [
                "Biogas",
                f"`monthly_m3 = daily_biogas_m3 x working_days`; `gross = monthly_m3 x BIOGAS_ENERGY_PER_M3`; `delivered = gross x {fmt_number(biogas_eff, 2)}`",
            ],
            [
                "Traditional biomass",
                f"`gross = monthly_biomass_kg x BIOMASS_ENERGY_CONTENT`; `delivered = gross x {fmt_number(biomass_eff, 2)}`",
            ],
            [
                "Mixed usage",
                "Run each selected commercial single-fuel branch independently, then sum `monthly_energy_kwh`, `monthly_cost`, and `annual_emissions`.",
            ],
            [
                "Dish-based",
                "`Final_Energy_Value = dish_energy x scaling_factor x serving_volume_efficiency x wastage_factor x monthly_servings`; environmental grade is based on `annual_co2 / annual_servings`.",
            ],
        ],
    )

    lines.append("### Commercial Consumption Combination Matrix (Single-Fuel And Submethod Branches)")
    lines.append("")
    append_table(
        lines,
        ["Institution", "Primary fuel", "Variant", "Example form inputs", "Fuel breakdown", "Monthly energy", "Monthly cost", "Annual CO2", "Cost/serving", "Health", "Env grade"],
        [
            [
                row["institution_type"],
                row["primary_fuel"],
                row["variant"],
                form_input_text(row["form"]),
                fuel_breakdown_summary(row["result"]),
                fmt_number(row["result"]["monthly_energy_kwh"]),
                fmt_money(row["result"]["monthly_cost"]),
                fmt_number(row["result"]["annual_emissions"]),
                fmt_money(row["result"].get("cost_per_serving", 0)),
                f"{fmt_number(row['health']['health_risk_score'])} ({row['health']['health_risk_category']})",
                row["result"].get("environmental_grade", ""),
            ]
            for row in consumption_variants["single_rows"]
        ],
    )

    lines.append("### Commercial Mixed-Usage Subset Matrix (All 15 Fuel Toggle Combinations For Every Institution)")
    lines.append("")
    append_table(
        lines,
        ["Institution", "Fuel mix", "Example form inputs", "Fuel breakdown", "Monthly energy", "Monthly cost", "Annual CO2", "Cost/serving", "Health", "Env grade"],
        [
            [
                row["institution_type"],
                row["variant"],
                form_input_text(row["form"]),
                fuel_breakdown_summary(row["result"]),
                fmt_number(row["result"]["monthly_energy_kwh"]),
                fmt_money(row["result"]["monthly_cost"]),
                fmt_number(row["result"]["annual_emissions"]),
                fmt_money(row["result"].get("cost_per_serving", 0)),
                f"{fmt_number(row['health']['health_risk_score'])} ({row['health']['health_risk_category']})",
                row["result"].get("environmental_grade", ""),
            ]
            for row in consumption_variants["mixed_rows"]
        ],
    )

    lines.append("### Commercial Consumption-Based Worked Examples")
    lines.append("")
    for name, example in payload["consumption_examples"].items():
        result = example["result"]
        institution = example["institution"]
        lines.append(f"#### {name}")
        lines.append("")
        append_table(
            lines,
            ["Institution field", "Value"],
            [
                ["institution_type", institution["institution_type"]],
                ["servings_per_day", institution["servings_per_day"]],
                ["working_days", institution["working_days"]],
                ["district", institution["district"]],
                ["electricity_tariff", institution["electricity_tariff"]],
                ["available_roof_area", institution["available_roof_area"]],
            ],
        )
        append_table(lines, ["Form input", "Value"], [[k, v] for k, v in example["form"].items(multi=True)])

        fuel_breakdown = result["fuel_details"]["fuel_breakdown"]
        append_table(
            lines,
            ["Fuel", "Useful kWh/month", "Monthly cost", "Annual CO2", "Quantity", "Unit"],
            [
                [
                    fuel_name,
                    fmt_number(details.get("energy_delivered", details.get("delivered_energy_kwh", 0)), 3),
                    fmt_money(details.get("monthly_cost", 0)),
                    fmt_number(emissions_value(details), 2),
                    fmt_number(details.get("quantity", details.get("monthly_scm", details.get("monthly_kg", 0))), 3),
                    details.get("unit", ""),
                ]
                for fuel_name, details in fuel_breakdown.items()
            ],
        )

        if name == "School LPG":
            monthly_factor = institution["working_days"]
            domestic_gross = 1 * 14.2 * helper.LPG_CALORIFIC_VALUE
            commercial_gross = 4 * 19.0 * helper.LPG_CALORIFIC_VALUE
            efficiency = lpg_eff
            lines.append("Key formulas:")
            lines.append(f"1. `domestic_gross = 1 x 14.2 x {fmt_number(helper.LPG_CALORIFIC_VALUE)} = {fmt_number(domestic_gross)} kWh`")
            lines.append(f"2. `commercial_gross = 4 x 19.0 x {fmt_number(helper.LPG_CALORIFIC_VALUE)} = {fmt_number(commercial_gross)} kWh`")
            lines.append(f"3. `useful_energy = ({fmt_number(domestic_gross)} + {fmt_number(commercial_gross)}) x {fmt_number(efficiency, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
            lines.append(f"4. Commercial annualization uses `annual_days = {monthly_factor} x 12 = {monthly_factor * 12}` days")
        elif name == "Anganwadi PNG":
            png_rate = as_float(db_helper.get_png_pricing(district=institution["district"], category="Commercial")["price_per_scm"])
            png_details = fuel_breakdown["PNG"]
            lines.append("Key formulas:")
            lines.append("1. Bill input is reverse-solved to monthly SCM with `calculate_png_consumption_from_bill()`.")
            lines.append(f"2. `rate_per_scm = {fmt_number(png_rate, 2)}` from `fuel_unit_pricing`.")
            lines.append(f"3. `useful_energy = gross_energy x {fmt_number(png_eff, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`.")
            lines.append(f"4. `annual_co2 = (gross_energy / {institution['working_days']}) x ({institution['working_days']} x 12) x {fmt_number(helper.EMISSION_FACTORS['PNG'], 3)} = {fmt_number(png_details['annual_co2_kg'])} kg/year`.")
        elif name == "Hotel Grid electricity":
            lines.append("Key formulas:")
            lines.append(f"1. `monthly_cost = 900 x {fmt_number(institution['electricity_tariff'], 2)} = {fmt_money(result['monthly_cost'])}`")
            lines.append(f"2. `monthly_useful_energy = 900 x {fmt_number(grid_eff, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
        elif name == "Factory Biogas":
            biogas = fuel_breakdown["Biogas"]
            lines.append("Key formulas:")
            lines.append(f"1. `monthly_m3 = daily_biogas_m3 x working_days = 12 x {institution['working_days']} = {fmt_number(biogas['monthly_m3'])} m3`")
            lines.append(f"2. `gross_energy = monthly_m3 x {fmt_number(biogas['energy_per_m3_kwh'], 2)} = {fmt_number(biogas['gross_energy_kwh'])} kWh`")
            cost_components = biogas.get("cost_components", {})
            lines.append(f"3. `monthly_cost = feedstock + maintenance + EMI + user_opex = {fmt_money(cost_components.get('feedstock_cost', 0))} + {fmt_money(cost_components.get('maintenance_cost', 0))} + {fmt_money(cost_components.get('capex_component', 0))} + {fmt_money(cost_components.get('user_opex', 0))} = {fmt_money(result['monthly_cost'])}`")
        elif name == "Community Kitchen Biomass":
            biomass = fuel_breakdown["Traditional Solid Biomass"]
            lines.append("Key formulas:")
            lines.append(f"1. `gross_energy = 350 x {fmt_number(biomass.get('energy_per_kg_kwh', 4.5), 2)} = {fmt_number(biomass['gross_energy_kwh'])} kWh`")
            lines.append(f"2. `useful_energy = gross_energy x {fmt_number(biomass_eff, 2)} = {fmt_number(result['monthly_energy_kwh'])} kWh`")
            lines.append(f"3. `annual_co2 = (gross_energy / 30) x 360 x {fmt_number(helper.EMISSION_FACTORS['Traditional Solid Biomass'], 3)} = {fmt_number(result['annual_emissions'])} kg/year`")
        else:
            lines.append("Mixed example total:")
            lines.append(f"- monthly_energy_kwh = {fmt_number(result['monthly_energy_kwh'])}")
            lines.append(f"- monthly_cost = {fmt_money(result['monthly_cost'])}")
            lines.append(f"- annual_emissions = {fmt_number(result['annual_emissions'])}")
        lines.append("")
        append_alternative_analysis(lines, example.get("alternatives", {}), example.get("recommendations", []))

    lines.append("### Commercial Dish Combination Inventory")
    lines.append("")
    append_table(
        lines,
        ["Institution", "Canonical dish count", "Canonical dishes used in the matrix", "Fuel pool", "Fuel subsets", "Total assignment patterns"],
        [
            [
                institution_type,
                len(subset_payload["base_dishes"]),
                "<br>".join(f"{row['dish_name']} ({row['category_name']})" for row in subset_payload["base_dishes"]),
                mix_label(subset_payload["fuel_pool"]),
                len(subset_payload["subset_rows"]),
                total_assignment_patterns(len(subset_payload["fuel_pool"]), len(subset_payload["base_dishes"])),
            ]
            for institution_type, subset_payload in dish_subset_examples.items()
        ],
    )
    lines.append("As in residential mode, `current_fuel_mix` only constrains the form UI. The backend result is driven by the actual `dish_name_fuel` assignment stored per selected dish.")
    lines.append("")
    for institution_type, subset_payload in dish_subset_examples.items():
        lines.append(f"### Commercial Dish Fuel-Subset Matrix ({institution_type})")
        lines.append("")
        append_table(
            lines,
            ["Fuel mix", "Assigned dishes", "Unused selected fuels", "Dish count", "Theoretical assignments", "Monthly energy", "Monthly cost", "Annual CO2", "Cost/serving", "Health", "Env grade"],
            [
                [
                    mix_label(row["fuel_mix"]),
                    "<br>".join(row["assignment"]),
                    ", ".join(row["unused_fuels"]) if row["unused_fuels"] else "-",
                    row["dish_count"],
                    row["assignment_count"],
                    fmt_number(row["result"]["monthly_energy_kwh"]),
                    fmt_money(row["result"]["monthly_cost"]),
                    fmt_number(row["result"]["annual_emissions"]),
                    fmt_money(row["result"].get("cost_per_serving", 0)),
                    f"{fmt_number((health := health_snapshot(row['result'], payload['dish_examples'][institution_type]['kitchen']))['health_risk_score'])} ({health['health_risk_category']})",
                    row["result"].get("environmental_grade", ""),
                ]
                for row in subset_payload["subset_rows"]
            ],
        )

    lines.append("### Commercial Dish-Based Worked Example (Hotel, full multi-meal case)")
    lines.append("")
    hotel = payload["dish_examples"]["Hotel"]
    append_table(
        lines,
        ["Selected dish", "Category", "Assigned fuel"],
        [[row["Dishes"], row["Category"], row["stoves"]] for row in hotel["selection_rows"]],
    )
    append_table(lines, ["Meal intensity", "Value"], [[k, v] for k, v in hotel["meal_types"].items()])
    lines.append(f"Serving volume efficiency = {fmt_number(hotel['debug']['serving_efficiency'], 2)}")
    lines.append(f"Commercial wastage factor = {fmt_number(hotel['debug']['wastage_factor'], 3)}")
    lines.append("")
    append_table(
        lines,
        ["Category", "Intensity", "Target calories/month", "Actual calories/serving", "Scaling factor", "Useful energy/month"],
        [
            [
                row["category"],
                row["meal_intensity"],
                fmt_number(row["target_calories_monthly"], 0),
                fmt_number(row["actual_calories_per_serving"], 2),
                fmt_number(row["scaling_factor"], 4),
                fmt_number(row["monthly_energy_kwh"], 3),
            ]
            for row in hotel["debug"]["categories"]
        ],
    )
    append_table(
        lines,
        ["Dish", "Category", "Fuel", "Portion g", "Calories/100g", "Dish calories", "Base dish energy", "Final useful energy"],
        [
            [
                row["Dishes"],
                row["Category"],
                row["stoves"],
                fmt_number(row.get("minimum_portion_g", 0), 0),
                fmt_number(row.get("calories_per_100g", 0), 2),
                fmt_number(row.get("total_calories", 0), 2),
                fmt_number(row.get("energy_to_cook_kwh", 0), 4),
                fmt_number(row.get("Final_Energy_Value", 0), 4),
            ]
            for _, row in hotel["debug"]["energy_df"].iterrows()
        ],
    )
    append_table(
        lines,
        ["Fuel", "Useful kWh/month", "Energy required", "Monthly cost", "Annual CO2", "Cost per kWh"],
        [
            [
                fuel_name,
                fmt_number(details["energy_delivered"], 3),
                fmt_number(details["energy_required"], 3),
                fmt_money(details["monthly_cost"]),
                fmt_number(details["annual_emissions"], 2),
                fmt_number(details["cost_per_kwh"], 3),
            ]
            for fuel_name, details in hotel["result"]["fuel_details"]["fuel_breakdown"].items()
        ],
    )
    append_table(
        lines,
        ["Hotel dish-based output", "Value"],
        [
            ["monthly_energy_kwh", fmt_number(hotel["result"]["monthly_energy_kwh"])],
            ["monthly_cost", fmt_money(hotel["result"]["monthly_cost"])],
            ["annual_emissions", fmt_number(hotel["result"]["annual_emissions"])],
            ["cost_per_serving", fmt_money(hotel["result"]["cost_per_serving"])],
            ["energy_per_serving_kwh", fmt_number(hotel["result"]["energy_per_serving_kwh"], 4)],
            ["environmental_grade", hotel["result"].get("environmental_grade", "")],
        ],
    )

    lines.append("### Commercial Dish-Based Summary For All Institution Types")
    lines.append("")
    append_table(
        lines,
        ["Institution type", "Selected categories", "Monthly energy", "Monthly cost", "Annual CO2", "Cost/serving", "Env grade"],
        [
            [
                name,
                ", ".join(row["Category"] for row in example["selection_rows"]) or "No meal categories found",
                fmt_number(example["result"]["monthly_energy_kwh"]),
                fmt_money(example["result"]["monthly_cost"]),
                fmt_number(example["result"]["annual_emissions"]),
                fmt_money(example["result"]["cost_per_serving"]),
                example["result"].get("environmental_grade", ""),
            ]
            for name, example in payload["dish_examples"].items()
        ],
    )

    lines.append("### Commercial Analysis Example Based On The Hotel Dish Mix")
    lines.append("")
    append_table(
        lines,
        ["Current health metric", "Value"],
        [
            ["pm25_peak", fmt_number(payload["hotel_analysis"]["health"]["pm25_peak"], 3)],
            ["health_risk_score", fmt_number(payload["hotel_analysis"]["health"]["health_risk_score"], 2)],
            ["health_risk_category", payload["hotel_analysis"]["health"]["health_risk_category"]],
        ],
    )
    append_table(
        lines,
        ["Alternative fuel", "Monthly cost", "Annual CO2", "Health risk", "Env grade"],
        [
            [
                fuel_name,
                fmt_money(data.get("monthly_cost", 0)),
                fmt_number(emissions_value(data), 2),
                fmt_number(data.get("health_risk_score", 0), 2),
                data.get("environmental_grade", ""),
            ]
            for fuel_name, data in payload["hotel_analysis"]["alternatives"].items()
        ],
    )
    append_table(
        lines,
        ["Rank", "Fuel", "Weighted score", "Monthly cost", "Annual CO2"],
        [
            [
                index + 1,
                recommendation[0],
                fmt_number(recommendation[1], 2),
                fmt_money(recommendation[2].get("monthly_cost", 0)),
                fmt_number(emissions_value(recommendation[2]), 2),
            ]
            for index, recommendation in enumerate(payload["hotel_analysis"]["recommendations"])
        ],
    )


def append_watchlist(lines: list[str], reference: dict[str, Any]) -> None:
    lines.append("## Debug Watchlist")
    lines.append("")
    lines.append("The following items are the most likely places to check first when a number looks wrong:")
    lines.append("")
    lines.append("1. `BIOMASS_ENERGY_CONTENT` and solar GHI/system efficiency are requested through alias names. The app now resolves them to the DB rows shown in the parameter snapshot.")
    lines.append("2. `PNG_FIXED_CHARGE_MONTHLY` and `PNG_METER_RENT_MONTHLY` are missing in the current DB, so PNG bill calculations are variable-charge only unless those rows are added.")
    lines.append("3. `ELECTRICITY_RESIDENTIAL_RATE`, `ELECTRICITY_COMMERCIAL_RATE`, and `Keralam_WEATHER_FACTOR` are currently falling back to code defaults when no DB row exists.")
    lines.append(f"4. `Traditional Solid Biomass` now resolves through the DB-backed thermal-efficiency map to `{fmt_number(get_reference_efficiency(reference, 'Traditional Solid Biomass', 0.0), 2)}`. If this row changes in `thermal_efficiencies`, both consumption and dish calculations will change with it.")
    lines.append("5. Multi-fuel health impact is now computed from the weighted fuel mix instead of collapsing to a single synthetic fuel label. If you compare against older reports, this value can change.")
    lines.append("6. Commercial annual CO2 always needs `working_days`; if `working_days` changes, emissions and per-serving metrics should change immediately.")
    lines.append("7. Residential LPG DB rows contain both `unit_price=850` and `subsidized_unit_price=600`, but `get_lpg_pricing()` currently feeds `unit_price` into the residential fallback path. If the user leaves `cylinder_price` blank, this can explain mismatches.")
    lines.append("")
    lines.append("## Regeneration")
    lines.append("")
    lines.append("Regenerate this guide after any DB or formula change with:")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 scripts/generate_technical_debug_guide.py")
    lines.append("```")
    lines.append("")


def main() -> None:
    disable_logging()
    reference = get_reference_snapshot()
    residential = residential_examples()
    commercial = commercial_examples()

    lines: list[str] = []
    append_intro(lines, reference)
    append_residential(lines, reference, residential)
    append_commercial(lines, reference, commercial)
    append_watchlist(lines, reference)

    OUTPUT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
