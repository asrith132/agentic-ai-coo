"""
app/agents/finance/tools.py

Transaction ingestion and financial analysis helpers for FinanceAgent.

Tools used by FinanceAgent:
- ingest_financial_csv()           -> parse, normalize, categorize, and persist transactions
- compute_financial_snapshot()     -> derive burn, revenue, net, and runway from stored data
- detect_spending_anomalies()      -> flag unusual spending relative to historical baseline
- generate_plain_english_summary() -> turn metrics into founder-friendly summaries

Environment variables expected:
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY   (preferred for backend writes)
  or
- SUPABASE_ANON_KEY           (fallback)

Schema assumptions:
finance_transactions:
  - date
  - description
  - amount
  - category
  - subcategory
  - is_recurring
  - source
  - notes

finance_snapshots:
  - month
  - total_income
  - total_expenses
  - net
  - by_category
  - runway_months
  - current_balance

Sign convention:
- income > 0
- expense < 0
"""

from __future__ import annotations

import csv
import io
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Tuple

from supabase import Client, create_client


ALLOWED_CATEGORIES = {
  "hosting",
  "tools",
  "contractors",
  "marketing",
  "salary",
  "revenue",
  "tax",
  "legal",
  "other",
}

ALLOWED_SOURCES = {"csv", "manual", "plaid"}


class FinanceConfigError(RuntimeError):
  """Raised when required finance configuration is missing."""


class FinanceDataError(RuntimeError):
  """Raised when input data is malformed or cannot be processed."""


@dataclass
class ParsedTransaction:
  date: str
  description: str
  amount: float
  category: str
  subcategory: Optional[str]
  is_recurring: bool
  source: str
  notes: Optional[str]


def _get_supabase() -> Client:
  url = os.getenv("SUPABASE_URL")
  key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

  if not url or not key:
      raise FinanceConfigError(
          "Missing Supabase configuration. Expected SUPABASE_URL and "
          "SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY."
      )

  return create_client(url, key)


def _clean_header(value: str) -> str:
  return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _to_decimal(raw: Any) -> Decimal:
  if raw is None:
      raise FinanceDataError("Amount value is missing.")

  s = str(raw).strip()
  if not s:
      raise FinanceDataError("Amount value is empty.")

  negative = False

  if s.startswith("(") and s.endswith(")"):
      negative = True
      s = s[1:-1].strip()

  s = s.replace("$", "").replace(",", "").strip()

  if s.endswith("-"):
      negative = True
      s = s[:-1].strip()

  if s.startswith("-"):
      negative = True
      s = s[1:].strip()

  try:
      value = Decimal(s)
  except InvalidOperation as exc:
      raise FinanceDataError(f"Invalid amount value: {raw}") from exc

  return -value if negative else value


def _normalize_date(raw: Any) -> str:
  if raw is None:
      raise FinanceDataError("Transaction date is missing.")

  value = str(raw).strip()
  if not value:
      raise FinanceDataError("Transaction date is empty.")

  date_formats = [
      "%Y-%m-%d",
      "%m/%d/%Y",
      "%m/%d/%y",
      "%d/%m/%Y",
      "%Y/%m/%d",
      "%b %d %Y",
      "%B %d %Y",
  ]

  for fmt in date_formats:
      try:
          return datetime.strptime(value, fmt).date().isoformat()
      except ValueError:
          continue

  try:
      return datetime.fromisoformat(value).date().isoformat()
  except ValueError as exc:
      raise FinanceDataError(f"Unsupported date format: {raw}") from exc


def _month_start(value: str | date | datetime) -> str:
  if isinstance(value, str):
      d = datetime.fromisoformat(value).date()
  elif isinstance(value, datetime):
      d = value.date()
  else:
      d = value
  return d.replace(day=1).isoformat()


def _extract_rows(csv_content: str) -> List[Dict[str, str]]:
  reader = csv.DictReader(io.StringIO(csv_content))
  if not reader.fieldnames:
      raise FinanceDataError("CSV appears to be missing headers.")

  cleaned_fieldnames = [_clean_header(name) for name in reader.fieldnames]
  rows: List[Dict[str, str]] = []

  for raw_row in reader:
      cleaned_row: Dict[str, str] = {}
      for original_key, cleaned_key in zip(reader.fieldnames, cleaned_fieldnames):
          cleaned_row[cleaned_key] = raw_row.get(original_key, "")
      rows.append(cleaned_row)

  return rows


def _find_first_key(row: Dict[str, Any], candidates: Iterable[str]) -> Optional[str]:
  for key in candidates:
      if key in row and str(row[key]).strip():
          return key
  return None


def _infer_description(row: Dict[str, Any]) -> str:
  key = _find_first_key(
      row,
      [
          "description",
          "name",
          "merchant",
          "payee",
          "details",
          "memo",
          "transaction_description",
      ],
  )
  if not key:
      return "Unknown transaction"
  return str(row[key]).strip()


def _infer_date(row: Dict[str, Any]) -> str:
  key = _find_first_key(
      row,
      ["date", "transaction_date", "posted_date", "created", "effective_date"],
  )
  if not key:
      raise FinanceDataError("Could not find a usable date column in CSV.")
  return _normalize_date(row[key])


def _infer_amount(row: Dict[str, Any]) -> Decimal:
  amount_key = _find_first_key(row, ["amount", "transaction_amount", "value"])
  debit_key = _find_first_key(row, ["debit", "withdrawal", "money_out"])
  credit_key = _find_first_key(row, ["credit", "deposit", "money_in"])
  type_key = _find_first_key(row, ["type", "transaction_type", "direction"])

  if amount_key:
      amount = _to_decimal(row[amount_key])

      if type_key:
          tx_type = str(row[type_key]).strip().lower()
          if tx_type in {"debit", "expense", "outflow", "withdrawal", "payment"}:
              return -abs(amount)
          if tx_type in {"credit", "income", "inflow", "deposit", "payout"}:
              return abs(amount)

      description = _infer_description(row).lower()
      if amount > 0 and any(
          token in description for token in ["refund", "reversal", "chargeback"]
      ):
          return abs(amount)

      return amount

  if debit_key or credit_key:
      debit = _to_decimal(row[debit_key]) if debit_key else Decimal("0")
      credit = _to_decimal(row[credit_key]) if credit_key else Decimal("0")

      if credit and not debit:
          return abs(credit)
      if debit and not credit:
          return -abs(debit)
      return credit - debit

  raise FinanceDataError("Could not find a usable amount column in CSV.")


def _infer_balance(row: Dict[str, Any]) -> Optional[float]:
  key = _find_first_key(row, ["balance", "running_balance", "available_balance"])
  if not key:
      return None
  try:
      return float(_to_decimal(row[key]))
  except FinanceDataError:
      return None


def _infer_source(source: str) -> str:
  normalized = source.strip().lower()
  return normalized if normalized in ALLOWED_SOURCES else "csv"


def _categorize_transaction(description: str, amount: float) -> Tuple[str, Optional[str]]:
  text = description.lower()

  keyword_map = [
      ("revenue", ["stripe payout", "payment received", "customer payment", "invoice paid", "wire received", "sale"]),
      ("hosting", ["aws", "amazon web services", "gcp", "google cloud", "azure", "vercel", "render", "railway", "cloudflare", "digitalocean", "heroku", "fly.io", "netlify"]),
      ("tools", ["openai", "anthropic", "slack", "notion", "figma", "linear", "github", "cursor", "atlassian", "supabase", "twilio", "retell", "vapi", "zoom", "google workspace"]),
      ("contractors", ["upwork", "fiverr", "contractor", "freelancer", "consulting", "consultant"]),
      ("marketing", ["google ads", "meta ads", "facebook ads", "reddit ads", "linkedin ads", "marketing", "promotion", "sponsorship"]),
      ("salary", ["payroll", "gusto", "salary", "wages", "stipend"]),
      ("tax", ["irs", "franchise tax", "sales tax", "state tax", "tax payment"]),
      ("legal", ["lawyer", "attorney", "legalzoom", "clerk filing", "contract review", "incorporation"]),
  ]

  for category, keywords in keyword_map:
      for keyword in keywords:
          if keyword in text:
              return category, keyword

  if amount > 0:
      return "revenue", "income"

  return "other", None


def _detect_recurring_flags(transactions: List[ParsedTransaction]) -> Dict[Tuple[str, str, float], bool]:
  """
  Simple recurring heuristic:
    Same normalized description + category + rounded absolute amount
    appearing at least 2 times across different months => recurring.
  """
  occurrences: Dict[Tuple[str, str, float], set[str]] = defaultdict(set)

  for tx in transactions:
      month = tx.date[:7]
      key = (
          re.sub(r"\s+", " ", tx.description.lower()).strip(),
          tx.category,
          round(abs(tx.amount), 2),
      )
      occurrences[key].add(month)

  return {key: len(months) >= 2 for key, months in occurrences.items()}


def _fetch_existing_transactions(supabase: Client) -> List[Dict[str, Any]]:
  response = (
      supabase.table("finance_transactions")
      .select("date, description, amount, category")
      .execute()
  )
  return response.data or []


def ingest_financial_csv(
  csv_content: str,
  source: str = "csv",
  notes: Optional[str] = None,
  replace_existing: bool = False,
) -> Dict[str, Any]:
  """
  Parse, normalize, categorize, and persist transactions from a CSV export.

  Args:
      csv_content: raw CSV file content
      source: one of csv | manual | plaid
      notes: optional notes attached to ingested transactions
      replace_existing: if True, deletes existing transactions in overlapping date range
                        before inserting new ones

  Returns:
      Summary of ingestion results.
  """
  supabase = _get_supabase()
  rows = _extract_rows(csv_content)

  parsed: List[ParsedTransaction] = []
  latest_balance: Optional[float] = None
  normalized_source = _infer_source(source)

  for row in rows:
      tx_date = _infer_date(row)
      description = _infer_description(row)
      amount = float(_infer_amount(row))
      category, subcategory = _categorize_transaction(description, amount)
      balance = _infer_balance(row)

      if balance is not None:
          latest_balance = balance

      parsed.append(
          ParsedTransaction(
              date=tx_date,
              description=description,
              amount=amount,
              category=category,
              subcategory=subcategory,
              is_recurring=False,
              source=normalized_source,
              notes=notes,
          )
      )

  existing = _fetch_existing_transactions(supabase)
  combined_for_recurring = parsed + [
      ParsedTransaction(
          date=str(tx["date"]),
          description=str(tx["description"]),
          amount=float(tx["amount"]),
          category=str(tx["category"]),
          subcategory=None,
          is_recurring=False,
          source="csv",
          notes=None,
      )
      for tx in existing
  ]

  recurring_flags = _detect_recurring_flags(combined_for_recurring)

  insert_rows: List[Dict[str, Any]] = []
  for tx in parsed:
      recurring_key = (
          re.sub(r"\s+", " ", tx.description.lower()).strip(),
          tx.category,
          round(abs(tx.amount), 2),
      )
      tx.is_recurring = recurring_flags.get(recurring_key, False)

      insert_rows.append(
          {
              "date": tx.date,
              "description": tx.description,
              "amount": tx.amount,
              "category": tx.category if tx.category in ALLOWED_CATEGORIES else "other",
              "subcategory": tx.subcategory,
              "is_recurring": tx.is_recurring,
              "source": tx.source,
              "notes": tx.notes,
          }
      )

  if not insert_rows:
      return {
          "rows_processed": 0,
          "rows_inserted": 0,
          "income_count": 0,
          "expense_count": 0,
          "latest_balance": latest_balance,
          "date_range": None,
      }

  min_date = min(row["date"] for row in insert_rows)
  max_date = max(row["date"] for row in insert_rows)

  if replace_existing:
      (
          supabase.table("finance_transactions")
          .delete()
          .gte("date", min_date)
          .lte("date", max_date)
          .eq("source", normalized_source)
          .execute()
      )

  response = supabase.table("finance_transactions").insert(insert_rows).execute()

  if hasattr(response, "error") and response.error:
      print("SUPABASE INSERT ERROR:", response.error)
      raise Exception(response.error)

  inserted = response.data or []

  return {
      "rows_processed": len(rows),
      "rows_inserted": len(inserted),
      "income_count": sum(1 for row in insert_rows if row["amount"] > 0),
      "expense_count": sum(1 for row in insert_rows if row["amount"] < 0),
      "latest_balance": latest_balance,
      "date_range": {"start": min_date, "end": max_date},
      "categories_found": sorted({row["category"] for row in insert_rows}),
  }


def _fetch_transactions_for_range(
  supabase: Client,
  start_date: str,
  end_date: str,
) -> List[Dict[str, Any]]:
  response = (
      supabase.table("finance_transactions")
      .select("*")
      .gte("date", start_date)
      .lte("date", end_date)
      .order("date")
      .execute()
  )
  return response.data or []


def compute_financial_snapshot(
  month: Optional[str] = None,
  current_balance: Optional[float] = None,
) -> Dict[str, Any]:
  """
  Compute and persist a monthly financial snapshot.

  Args:
      month: any ISO date string within the month, or YYYY-MM-01. Defaults to current month.
      current_balance: optional latest balance. If not provided, runway may be None.

  Returns:
      Saved snapshot dict.
  """
  supabase = _get_supabase()

  if month is None:
      month_start = date.today().replace(day=1).isoformat()
  else:
      month_start = _month_start(month)

  month_date = datetime.fromisoformat(month_start).date()

  if month_date.month == 12:
      next_month = date(month_date.year + 1, 1, 1)
  else:
      next_month = date(month_date.year, month_date.month + 1, 1)

  txs = _fetch_transactions_for_range(
      supabase=supabase,
      start_date=month_start,
      end_date=(next_month.fromordinal(next_month.toordinal() - 1)).isoformat(),
  )

  total_income = round(sum(float(tx["amount"]) for tx in txs if float(tx["amount"]) > 0), 2)
  total_expenses = round(
      abs(sum(float(tx["amount"]) for tx in txs if float(tx["amount"]) < 0)), 2
  )
  net = round(total_income - total_expenses, 2)

  by_category: Dict[str, float] = defaultdict(float)
  for tx in txs:
      amount = float(tx["amount"])
      if amount < 0:
          by_category[str(tx["category"])] += abs(amount)

  by_category = {
      category: round(value, 2)
      for category, value in sorted(by_category.items(), key=lambda item: item[1], reverse=True)
  }

  monthly_burn = total_expenses
  runway_months: Optional[float] = None
  if current_balance is not None and monthly_burn > 0:
      runway_months = round(current_balance / monthly_burn, 2)

  snapshot_payload = {
      "month": month_start,
      "total_income": total_income,
      "total_expenses": total_expenses,
      "net": net,
      "by_category": by_category,
      "runway_months": runway_months,
      "current_balance": current_balance,
  }

  response = (
      supabase.table("finance_snapshots")
      .upsert(snapshot_payload, on_conflict="month")
      .execute()
  )

  saved = response.data[0] if response.data else snapshot_payload
  return saved


def _previous_month_starts(month_start: str, count: int) -> List[str]:
  d = datetime.fromisoformat(month_start).date()
  results: List[str] = []
  year = d.year
  month = d.month

  for _ in range(count):
      month -= 1
      if month == 0:
          month = 12
          year -= 1
      results.append(date(year, month, 1).isoformat())

  return results


def _fetch_snapshots_by_months(
  supabase: Client,
  months: List[str],
) -> List[Dict[str, Any]]:
  if not months:
      return []
  response = (
      supabase.table("finance_snapshots")
      .select("*")
      .in_("month", months)
      .execute()
  )
  return response.data or []


def detect_spending_anomalies(
  month: Optional[str] = None,
  lookback_months: int = 3,
  threshold_percent: float = 100.0,
  min_absolute_increase: float = 200.0,
) -> List[Dict[str, Any]]:
  """
  Compare current month category spend against average historical spend.

  Args:
      month: target month. Defaults to current month.
      lookback_months: number of previous months to compare against
      threshold_percent: required percent increase over baseline
      min_absolute_increase: required absolute dollar increase over baseline

  Returns:
      List of anomaly dicts, ready for event emission.
  """
  supabase = _get_supabase()

  target_month = _month_start(month or date.today().isoformat())

  current_snapshots = _fetch_snapshots_by_months(supabase, [target_month])
  current_snapshot = current_snapshots[0] if current_snapshots else None
  if not current_snapshot:
      raise FinanceDataError(
          f"No finance snapshot found for month {target_month}. "
          "Run compute_financial_snapshot() first."
      )

  history_months = _previous_month_starts(target_month, lookback_months)
  history_snapshots = _fetch_snapshots_by_months(supabase, history_months)

  historical_by_category: Dict[str, List[float]] = defaultdict(list)
  for snapshot in history_snapshots:
      by_category = snapshot.get("by_category") or {}
      for category, value in by_category.items():
          historical_by_category[str(category)].append(float(value))

  current_by_category = current_snapshot.get("by_category") or {}
  anomalies: List[Dict[str, Any]] = []

  for category, current_value_raw in current_by_category.items():
      current_value = float(current_value_raw)
      prior_values = historical_by_category.get(str(category), [])

      if not prior_values:
          if current_value >= min_absolute_increase:
              anomalies.append(
                  {
                      "category": str(category),
                      "amount": round(current_value, 2),
                      "historical_average": 0.0,
                      "deviation_percent": None,
                      "description": (
                          f"New or previously insignificant spend detected in {category}: "
                          f"${current_value:.2f} this month."
                      ),
                  }
              )
          continue

      historical_average = sum(prior_values) / len(prior_values)
      absolute_increase = current_value - historical_average
      deviation_percent = (
          (absolute_increase / historical_average) * 100 if historical_average > 0 else None
      )

      if (
          deviation_percent is not None
          and deviation_percent >= threshold_percent
          and absolute_increase >= min_absolute_increase
      ):
          anomalies.append(
              {
                  "category": str(category),
                  "amount": round(current_value, 2),
                  "historical_average": round(historical_average, 2),
                  "deviation_percent": round(deviation_percent, 2),
                  "description": (
                      f"Spending in {category} rose to ${current_value:.2f}, up "
                      f"{deviation_percent:.1f}% from the recent average of "
                      f"${historical_average:.2f}."
                  ),
              }
          )

  anomalies.sort(key=lambda item: item["amount"], reverse=True)
  return anomalies


def generate_plain_english_summary(
  snapshot: Dict[str, Any],
  anomalies: Optional[List[Dict[str, Any]]] = None,
) -> str:
  """
  Convert a finance snapshot into a founder-friendly English summary.
  """
  anomalies = anomalies or []

  total_income = float(snapshot.get("total_income") or 0)
  total_expenses = float(snapshot.get("total_expenses") or 0)
  runway_months = snapshot.get("runway_months")
  by_category = snapshot.get("by_category") or {}

  parts: List[str] = []
  parts.append(
      f"You brought in ${total_income:,.2f} and spent ${total_expenses:,.2f} this month."
  )

  if by_category:
      top_category, top_amount = max(
          by_category.items(), key=lambda item: float(item[1])
      )
      parts.append(
          f"Your biggest expense category was {top_category} at ${float(top_amount):,.2f}."
      )

  if runway_months is not None:
      parts.append(
          f"At your current burn rate, you have about {float(runway_months):.1f} months of runway remaining."
      )
  else:
      parts.append(
          "Runway could not be calculated because no current balance was available."
      )

  if anomalies:
      top_anomaly = anomalies[0]
      parts.append(
          f"One thing to watch: {top_anomaly['description']}"
      )

  return " ".join(parts)