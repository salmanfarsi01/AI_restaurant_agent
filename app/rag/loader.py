"""
Loads restaurant knowledge into LangChain Documents from two sources:

1. The real menu/restaurant CSV export (data/raw/menu_dataset.csv) -- this is
   a change-log: each row is a Create/Update/Delete event for a menu item at
   a point in time, so multiple rows can describe the same item over time.
   We collapse this down to "current state" before indexing (see
   `_dedupe_to_latest_state`).

2. The synthetic bilingual policy files (data/raw/policy_en.txt / policy_bn.txt)
   -- the CSV has no terms/policy data, so this stays hand-written.

Note: the CSV is English-only. We deliberately do NOT try to auto-translate
it into Bangla. Multilingual embedding models (BGE-M3, multilingual-e5, etc.)
map same-meaning text from different languages into the same vector space, so
a Bangla query can still retrieve these English menu chunks -- retrieval
still works cross-lingually, only the generation step needs the LLM to answer
in Bangla using English-sourced context. This is worth calling out explicitly
in your paper as a design decision / limitation.
"""
import re
from pathlib import Path

import pandas as pd
from langchain_core.documents import Document

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# Point this at your real 5000-row export. A small sample with the same
# schema lives at data/raw/menu_dataset_sample.csv for local testing.
MENU_CSV_PATH = RAW_DIR / "menu_dataset.csv"
MENU_CSV_SAMPLE_PATH = RAW_DIR / "menu_dataset_sample.csv"

EXPECTED_COLUMNS = [
    "createdOn", "changeOperation", "market", "city",
    "menuItemName", "menuItemDescription", "menuItemCurrentPrice", "menuItemPreviousPrice",
    "menuItemImageUrl", "menuItemCategory", "menuItemAverageRating", "menuItemRatingCount",
    "restaurantName", "restaurantDescription", "restaurantAddress", "restaurantImageUrl",
    "restaurantPriceRange", "restaurantLatitude", "restaurantLongitude",
]


def _parse_price(value) -> float | None:
    """'$2.19 ' -> 2.19 ; '' / NaN -> None"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    match = re.search(r"[\d.]+", str(value))
    return float(match.group()) if match else None


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8")
    # drop stray "Unnamed: N" columns from trailing commas in the source export
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing expected columns: {missing}")

    df["createdOn"] = pd.to_datetime(df["createdOn"], errors="coerce")
    # fall back to row order for any timestamp pandas couldn't parse, so
    # dedup ordering still works even on messy exports
    df["createdOn"] = df["createdOn"].fillna(pd.Timestamp.min)
    df["_row_order"] = range(len(df))
    return df


def _dedupe_to_latest_state(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse the change-log to one row per (restaurantName, menuItemName):
    the most recent event. Items whose latest event is 'Delete' are dropped
    (they're no longer on the live menu).
    """
    df = df.sort_values(["createdOn", "_row_order"])
    latest = df.groupby(["restaurantName", "menuItemName"], as_index=False).tail(1)
    latest = latest[latest["changeOperation"].str.lower() != "delete"]
    return latest


def _menu_item_documents(df: pd.DataFrame) -> list[Document]:
    docs = []
    for _, row in df.iterrows():
        price = _parse_price(row.get("menuItemCurrentPrice"))
        price_str = f"${price:.2f}" if price is not None else "price unavailable"
        rating = row.get("menuItemAverageRating")
        rating_str = (
            f"{rating:.1f}/5 ({int(row.get('menuItemRatingCount') or 0)} ratings)"
            if pd.notna(rating) else "unrated"
        )

        text = (
            f"{row['menuItemName']} — {price_str}. Category: {row.get('menuItemCategory', 'N/A')}. "
            f"Restaurant: {row['restaurantName']} ({row.get('city', 'N/A')}). "
            f"Rating: {rating_str}. "
            f"{row.get('menuItemDescription', '') or ''}"
        ).strip()

        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": "menu",
                    "lang": "en",
                    "restaurant_name": row["restaurantName"],
                    "city": row.get("city"),
                    "market": row.get("market"),
                    "category": row.get("menuItemCategory"),
                    "price": price,
                    "rating": float(rating) if pd.notna(rating) else None,
                    "image_url": row.get("menuItemImageUrl"),
                },
            )
        )
    return docs


def _restaurant_documents(df: pd.DataFrame) -> list[Document]:
    """One doc per unique restaurant, built from its first-seen row."""
    unique = df.drop_duplicates(subset=["restaurantName"])
    docs = []
    for _, row in unique.iterrows():
        text = (
            f"{row['restaurantName']} is located at {row.get('restaurantAddress', 'an address not on file')}, "
            f"{row.get('city', '')}. Cuisine/type: {row.get('restaurantDescription', 'N/A')}. "
            f"Price range: {row.get('restaurantPriceRange', 'N/A')}."
        )
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": "restaurant_info",
                    "lang": "en",
                    "restaurant_name": row["restaurantName"],
                    "city": row.get("city"),
                    "market": row.get("market"),
                    "latitude": row.get("restaurantLatitude"),
                    "longitude": row.get("restaurantLongitude"),
                    "price_range": row.get("restaurantPriceRange"),
                },
            )
        )
    return docs


def _load_policy_docs() -> list[Document]:
    """Synthetic bilingual policy text -- the CSV has no policy data."""
    docs = []
    for lang in ("en", "bn"):
        path = RAW_DIR / f"policy_{lang}.txt"
        if path.exists():
            docs.append(
                Document(
                    page_content=path.read_text(encoding="utf-8"),
                    metadata={"source": "policy", "lang": lang},
                )
            )
    return docs


def load_menu_csv_documents(csv_path: Path | None = None) -> list[Document]:
    path = csv_path or (MENU_CSV_PATH if MENU_CSV_PATH.exists() else MENU_CSV_SAMPLE_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"No menu CSV found at {MENU_CSV_PATH} or {MENU_CSV_SAMPLE_PATH}. "
            f"Place your 5000-row export at data/raw/menu_dataset.csv."
        )
    df = _read_csv(path)
    current = _dedupe_to_latest_state(df)
    return _menu_item_documents(current) + _restaurant_documents(current)


def load_all_documents() -> list[Document]:
    """Menu/restaurant docs from the CSV (English) + policy docs (EN + BN)."""
    return load_menu_csv_documents() + _load_policy_docs()


if __name__ == "__main__":
    all_docs = load_all_documents()
    print(f"Loaded {len(all_docs)} documents")
    by_source = {}
    for d in all_docs:
        by_source[d.metadata["source"]] = by_source.get(d.metadata["source"], 0) + 1
    print("Breakdown:", by_source)
    for d in all_docs[:3]:
        print("---")
        print(d.metadata)
        print(d.page_content[:150])
