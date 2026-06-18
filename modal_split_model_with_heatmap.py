"""
It calculates:
- public transport share
- car share
- CO2 per visitor
- total CO2
- break-even sustainability fee

It also saves heatmaps.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# USER INPUTS & ASSUMPTIONS

OUTPUT_DIR = Path("modal_split_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Experimental setup from the report
TRAIN_DISCOUNTS = [0.00, 0.25, 0.50, 0.75, 1.00]
SHUTTLE_FREQS_PER_HOUR = [3, 4, 5, 6]
PARKING_FEE_FRACTIONS_OF_TICKET = [0.00, 0.25, 0.50]

# Baseline values from the report / coarse assumptions
N_VISITORS = 10000
BASE_FESTIVAL_TICKET_PRICE_EUR = 45.00
NS_RETURN_FARE_EUR = 25.00
BASE_PUBLIC_TRANSPORT_SHARE = 0.15

# Baseline generalized costs and times
BASE_CAR_FUEL_COST_EUR = 15.00
BASE_CAR_PARKING_FEE_EUR = 0.00
BASE_PT_COST_EUR = NS_RETURN_FARE_EUR

BASE_CAR_TIME_MIN = 45.0
BASE_PT_IN_VEHICLE_TIME_MIN = 50.0
BASE_PT_WALK_TRANSFER_TIME_MIN = 15.0
BASE_SHUTTLE_FREQ_PER_HOUR = 3
OUT_OF_VEHICLE_TIME_WEIGHT = 2.0

# Elasticities used to calibrate beta values
PRICE_ELASTICITY_PT = -0.45
TIME_ELASTICITY_PT = -0.55

# CO2 assumptions. Adjust if you have measured/required factors.
CAR_EMISSIONS_G_PER_VISITOR = 4800.0
PT_EMISSIONS_G_PER_VISITOR = 900.0


def shuttle_wait_time_min(freq_per_hour: float) -> float:
    """Expected wait time for a scheduled shuttle with even headways."""
    headway_min = 60.0 / freq_per_hour
    return headway_min / 2.0


def public_transport_generalized_time(freq_per_hour: float) -> float:
    """PT time with out-of-vehicle time weighted more heavily."""
    wait = shuttle_wait_time_min(freq_per_hour)
    return BASE_PT_IN_VEHICLE_TIME_MIN + OUT_OF_VEHICLE_TIME_WEIGHT * (
        BASE_PT_WALK_TRANSFER_TIME_MIN + wait
    )


def calibrate_betas() -> tuple[float, float]:
    """Calibrate sensitivities from baseline elasticities."""
    s0 = BASE_PUBLIC_TRANSPORT_SHARE
    c0 = BASE_PT_COST_EUR
    t0 = public_transport_generalized_time(BASE_SHUTTLE_FREQ_PER_HOUR)
    beta_cost = PRICE_ELASTICITY_PT / (c0 * (1.0 - s0))
    beta_time = TIME_ELASTICITY_PT / (t0 * (1.0 - s0))
    return beta_cost, beta_time


def modal_split(train_discount: float, shuttle_freq_per_hour: float, parking_fee_eur: float) -> tuple[float, float]:
    """Binary incremental model with public transport and car modes."""
    s_pt0 = BASE_PUBLIC_TRANSPORT_SHARE
    s_car0 = 1.0 - s_pt0
    beta_cost, beta_time = calibrate_betas()

    base_pt_cost = BASE_PT_COST_EUR
    scenario_pt_cost = NS_RETURN_FARE_EUR * (1.0 - train_discount)
    delta_pt_cost = scenario_pt_cost - base_pt_cost

    base_pt_time = public_transport_generalized_time(BASE_SHUTTLE_FREQ_PER_HOUR)
    scenario_pt_time = public_transport_generalized_time(shuttle_freq_per_hour)
    delta_pt_time = scenario_pt_time - base_pt_time

    base_car_cost = BASE_CAR_FUEL_COST_EUR + BASE_CAR_PARKING_FEE_EUR
    scenario_car_cost = BASE_CAR_FUEL_COST_EUR + parking_fee_eur
    delta_car_cost = scenario_car_cost - base_car_cost
    delta_car_time = 0.0

    delta_v_pt = beta_cost * delta_pt_cost + beta_time * delta_pt_time
    delta_v_car = beta_cost * delta_car_cost + beta_time * delta_car_time

    numerator = s_pt0 * np.exp(delta_v_pt)
    denominator = numerator + s_car0 * np.exp(delta_v_car)
    s_pt = numerator / denominator
    s_car = 1.0 - s_pt
    return s_pt, s_car


def run_experiments() -> pd.DataFrame:
    rows = []
    for freq in SHUTTLE_FREQS_PER_HOUR:
        for discount in TRAIN_DISCOUNTS:
            for parking_fraction in PARKING_FEE_FRACTIONS_OF_TICKET:
                parking_fee = parking_fraction * BASE_FESTIVAL_TICKET_PRICE_EUR
                s_pt, s_car = modal_split(discount, freq, parking_fee)
                co2_per_visitor = s_pt * PT_EMISSIONS_G_PER_VISITOR + s_car * CAR_EMISSIONS_G_PER_VISITOR
                total_co2_kg = co2_per_visitor * N_VISITORS / 1000.0
                break_even_fee = discount * NS_RETURN_FARE_EUR * s_pt
                fee_revenue = break_even_fee * N_VISITORS
                discount_cost = discount * NS_RETURN_FARE_EUR * s_pt * N_VISITORS

                rows.append(
                    {
                        "shuttle_freq_per_hour": freq,
                        "train_discount_pct": int(discount * 100),
                        "parking_fee_pct_of_ticket": int(parking_fraction * 100),
                        "parking_fee_eur": parking_fee,
                        "public_transport_share": s_pt,
                        "car_share": s_car,
                        "co2_per_visitor_g": co2_per_visitor,
                        "total_co2_kg": total_co2_kg,
                        "break_even_sustainability_fee_eur": break_even_fee,
                        "fee_revenue_eur": fee_revenue,
                        "discount_cost_eur": discount_cost,
                        "budget_balance_eur": fee_revenue - discount_cost,
                    }
                )
    return pd.DataFrame(rows)


def save_heatmap(df: pd.DataFrame, value_column: str, title_prefix: str, filename_prefix: str) -> None:
    """Save one heatmap per parking fee."""
    for parking_fraction in PARKING_FEE_FRACTIONS_OF_TICKET:
        parking_pct = int(parking_fraction * 100)
        fee_eur = parking_fraction * BASE_FESTIVAL_TICKET_PRICE_EUR
        subset = df[df["parking_fee_pct_of_ticket"] == parking_pct]
        pivot = subset.pivot(
            index="shuttle_freq_per_hour",   # y-axis (3 at top -> 6 at bottom)
            columns="train_discount_pct",    # x-axis (0.0 -> 1.0)
            values=value_column,
        )

        fig, ax = plt.subplots(figsize=(8, 5))
        image = ax.imshow(pivot.values, aspect="auto")
        cbar = fig.colorbar(image, ax=ax)
        cbar.set_label(value_column.replace("_", " "))

        # x-axis: train discount, shown as a fraction (0.0, 0.25, ...) like the report
        ax.set_xticks(np.arange(len(pivot.columns)))
        ax.set_xticklabels([f"{x / 100:g}" for x in pivot.columns])
        # y-axis: shuttle frequency
        ax.set_yticks(np.arange(len(pivot.index)))
        ax.set_yticklabels([str(y) for y in pivot.index])
        ax.set_xlabel("Train discount")
        ax.set_ylabel("Shuttle frequency (per hour)")
        ax.set_title(f"{title_prefix} | Parking fee = \u20ac{fee_eur:.2f}")

        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                value = pivot.values[i, j]
                if "share" in value_column:
                    label = f"{value:.1%}"
                elif "co2" in value_column:
                    label = f"{value:.0f}"
                else:
                    label = f"\u20ac{value:.2f}"
                ax.text(j, i, label, ha="center", va="center")

        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / f"{filename_prefix}_parkingfee_{parking_pct}pct.png", dpi=200)
        plt.close(fig)


def main() -> None:
    df = run_experiments()
    results_path = OUTPUT_DIR / "modal_split_results.csv"
    df.to_csv(results_path, index=False)

    save_heatmap(
        df,
        value_column="public_transport_share",
        title_prefix="Public transport share",
        filename_prefix="heatmap_public_transport_share",
    )
    save_heatmap(
        df,
        value_column="co2_per_visitor_g",
        title_prefix="CO2 per visitor",
        filename_prefix="heatmap_co2_per_visitor",
    )
    save_heatmap(
        df,
        value_column="break_even_sustainability_fee_eur",
        title_prefix="Break-even sustainability fee",
        filename_prefix="heatmap_break_even_fee",
    )

    baseline = df[
        (df["train_discount_pct"] == 0)
        & (df["parking_fee_pct_of_ticket"] == 0)
        & (df["shuttle_freq_per_hour"] == BASE_SHUTTLE_FREQ_PER_HOUR)
    ].iloc[0]

    best_co2 = df.sort_values("co2_per_visitor_g").iloc[0]
    best_pt_share = df.sort_values("public_transport_share", ascending=False).iloc[0]

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)

    print("Saved results to:", results_path)
    print("Saved heatmaps to:", OUTPUT_DIR.resolve())
    print("\nBaseline scenario:")
    print(baseline.to_string())
    print("\nLowest CO2 scenario:")
    print(best_co2.to_string())
    print("\nHighest public transport share scenario:")
    print(best_pt_share.to_string())
    print("\nFirst 10 experimental rows:")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()