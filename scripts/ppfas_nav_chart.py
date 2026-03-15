"""Daily NAV chart for PPFAS Flexi Cap (last 6 months) using plotnine."""

from datetime import datetime, timedelta

import httpx
import polars as pl
from plotnine import (
    aes,
    element_text,
    geom_line,
    ggplot,
    labs,
    save_as_pdf_pages,
    scale_x_datetime,
    theme,
    theme_minimal,
)
from plotnine.themes.elements import element_blank

SCHEME_CODE = 122639
OUTPUT_PATH = "india/data/ppfas_nav_6m.png"


def fetch_nav_data(scheme_code: int) -> pl.DataFrame:
    url = f"https://api.mfapi.in/mf/{scheme_code}"
    resp = httpx.get(url, timeout=30)
    data = resp.json()

    records = []
    for item in data["data"]:
        date = datetime.strptime(item["date"], "%d-%m-%Y")
        nav = float(item["nav"])
        records.append({"date": date, "nav": nav})

    return pl.DataFrame(records).sort("date")


def main():
    print("Fetching PPFAS Flexi Cap NAV data...")
    df = fetch_nav_data(SCHEME_CODE)

    cutoff = datetime.now() - timedelta(days=180)
    df = df.filter(pl.col("date") >= cutoff)
    print(f"Got {len(df)} trading days in last 6 months")

    pdf = df.to_pandas()

    chart = (
        ggplot(pdf, aes(x="date", y="nav"))
        + geom_line(color="#2563eb", size=0.8)
        + scale_x_datetime(date_breaks="1 month", date_labels="%b %Y")
        + labs(
            title="PPFAS Flexi Cap - Daily NAV (6 Months)",
            x="",
            y="NAV (₹)",
        )
        + theme_minimal()
        + theme(
            figure_size=(10, 5),
            plot_title=element_text(size=14, weight="bold"),
            axis_text_x=element_text(rotation=45, ha="right"),
            panel_grid_minor=element_blank(),
        )
    )

    chart.save(OUTPUT_PATH, dpi=150)
    print(f"Chart saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
