export interface FinanceTransaction {
  id: string
  date: string
  description: string
  amount: number
  category: string
  subcategory: string | null
  is_recurring: boolean
  source: string
  notes: string | null
  created_at: string | null
}

export interface FinanceSnapshot {
  id?: string
  month: string
  total_income: number
  total_expenses: number
  net: number
  by_category: Record<string, number>
  runway_months: number | null
  current_balance: number | null
}

export interface SpendingAnomaly {
  category: string
  amount: number
  historical_average: number
  deviation_percent: number | null
  description: string
}

export interface FinanceStatus {
  agent: string
  status: string
  transaction_count: number
  latest_snapshot: {
    month: string
    runway_months: number | null
    monthly_burn: number
    monthly_revenue: number
    net: number
  } | null
}

export interface UploadResult {
  agent: string
  ingestion: {
    rows_processed: number
    rows_inserted: number
    income_count: number
    expense_count: number
    latest_balance: number | null
    date_range: { start: string; end: string } | null
    categories_found: string[]
  } | null
  snapshot: FinanceSnapshot
  anomalies: SpendingAnomaly[]
  summary: string
}
