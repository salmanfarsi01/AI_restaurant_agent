"""
Day-by-Day Google Sheets Service:
Synchronizes confirmed orders into daily tabs (Orders_YYYY-MM-DD)
and maintains an active marketing customer lead directory (Leads_Master).
Includes local CSV fallback when Google Service Account is unconfigured.
"""
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class SheetsService:

    @staticmethod
    def _get_gsheet_client():
        """Attempts to authenticate with Google Sheets API via service account."""
        if not settings.google_sheets_enabled:
            return None
        cred_path = Path(settings.google_service_account_file)
        if not cred_path.exists():
            log.warning("Google service account file not found at %s. Using local backup.", cred_path)
            return None

        try:
            import gspread
            client = gspread.service_account(filename=str(cred_path))
            return client
        except Exception as e:
            log.warning("Failed to connect to Google Sheets: %s. Using local backup.", e)
            return None

    @classmethod
    def sync_order_to_google_sheets(cls, order: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Idempotent sync:
        1. Appends or updates the row in the daily sheet (Orders_YYYY-MM-DD)
        2. Upserts customer record into Leads_Master
        """
        client = cls._get_gsheet_client()
        today_tab_name = f"Orders_{datetime.utcnow().strftime('%Y-%m-%d')}"
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        items_summary = ", ".join(f"{it.get('quantity', 1)}x {it.get('item_name')}" for it in order.get("items", []))
        row_data = [
            order.get("created_at", now_str),
            order.get("order_code"),
            order.get("customer_name"),
            order.get("customer_email"),
            order.get("customer_phone"),
            order.get("delivery_address"),
            items_summary,
            f"৳{order.get('total_amount', 0.0):.2f}",
            order.get("payment_method", "CASH_ON_DELIVERY"),
            order.get("status", "CONFIRMED"),
        ]

        if client:
            try:
                if settings.google_sheet_id:
                    sheet = client.open_by_key(settings.google_sheet_id)
                else:
                    sheet = client.open(settings.google_sheet_title)

                # 1. Daily Tab Management
                try:
                    worksheet = sheet.worksheet(today_tab_name)
                except Exception:
                    # Tab doesn't exist yet; create it with headers
                    worksheet = sheet.add_worksheet(title=today_tab_name, rows=500, cols=10)
                    headers = [
                        "Timestamp", "Order ID", "Customer Name", "Email Address",
                        "Phone Number", "Delivery Address", "Ordered Items",
                        "Total Amount", "Payment Method", "Status"
                    ]
                    worksheet.append_row(headers)

                # Idempotent Upsert Check (Column B = Order ID)
                col_b = worksheet.col_values(2)
                order_code = order.get("order_code")
                if order_code in col_b:
                    row_idx = col_b.index(order_code) + 1
                    worksheet.update_cell(row_idx, 10, order.get("status", "CONFIRMED"))
                    log.info("Google Sheets: Updated existing order %s at row %d", order_code, row_idx)
                else:
                    worksheet.append_row(row_data)
                    log.info("Google Sheets: Appended new order %s to %s", order_code, today_tab_name)

                # 2. Leads Master Tab Upsert
                try:
                    leads_sheet = sheet.worksheet("Leads_Master")
                except Exception:
                    leads_sheet = sheet.add_worksheet(title="Leads_Master", rows=1000, cols=8)
                    leads_headers = [
                        "Email", "Full Name", "Phone", "First Order Date",
                        "Last Order Date", "Total Orders", "Lifetime Spend", "Subscribed"
                    ]
                    leads_sheet.append_row(leads_headers)

                emails = leads_sheet.col_values(1)
                cust_email = order.get("customer_email")
                if cust_email in emails:
                    lead_row_idx = emails.index(cust_email) + 1
                    # Update last order date
                    leads_sheet.update_cell(lead_row_idx, 5, now_str)
                else:
                    leads_sheet.append_row([
                        cust_email,
                        order.get("customer_name"),
                        order.get("customer_phone"),
                        now_str,
                        now_str,
                        1,
                        f"৳{order.get('total_amount', 0.0):.2f}",
                        "TRUE",
                    ])

                return True, "Synced successfully to Google Sheets."
            except Exception as e:
                log.warning("Error during Google Sheets API write: %s. Falling back to local CSV.", e)

        # Fallback to local daily CSV
        return cls._sync_to_local_csv(today_tab_name, row_data, order)

    @classmethod
    def _sync_to_local_csv(cls, tab_name: str, row_data: List[Any], order: Dict[str, Any]) -> Tuple[bool, str]:
        """Local file-based backup to ensure zero data loss."""
        Path(settings.sheets_backup_dir).mkdir(parents=True, exist_ok=True)
        csv_path = Path(settings.sheets_backup_dir) / f"{tab_name}.csv"
        leads_csv_path = Path(settings.sheets_backup_dir) / "Leads_Master.csv"

        headers = [
            "Timestamp", "Order ID", "Customer Name", "Email Address",
            "Phone Number", "Delivery Address", "Ordered Items",
            "Total Amount", "Payment Method", "Status"
        ]

        # 1. Write to daily CSV
        file_exists = csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(headers)
            writer.writerow(row_data)

        # 2. Write to Leads Master CSV
        leads_headers = [
            "Email", "Full Name", "Phone", "First Order Date",
            "Last Order Date", "Total Orders", "Lifetime Spend", "Subscribed"
        ]
        leads_exist = leads_csv_path.exists()
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with open(leads_csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not leads_exist:
                writer.writerow(leads_headers)
            writer.writerow([
                order.get("customer_email"),
                order.get("customer_name"),
                order.get("customer_phone"),
                now_str,
                now_str,
                1,
                f"৳{order.get('total_amount', 0.0):.2f}",
                "TRUE",
            ])

        log.info("Saved order data to local CSV replica at %s", csv_path)
        return True, f"Saved to local backup CSV {csv_path}"

    @classmethod
    def get_all_leads(cls) -> List[Dict[str, Any]]:
        """Retrieves active customer leads for marketing broadcast."""
        client = cls._get_gsheet_client()
        leads: List[Dict[str, Any]] = []

        if client:
            try:
                if settings.google_sheet_id:
                    sheet = client.open_by_key(settings.google_sheet_id)
                else:
                    sheet = client.open(settings.google_sheet_title)
                leads_sheet = sheet.worksheet("Leads_Master")
                records = leads_sheet.get_all_records()
                for r in records:
                    if str(r.get("Subscribed", "TRUE")).strip().upper() in ("TRUE", "1", "YES"):
                        leads.append({
                            "email": r.get("Email"),
                            "name": r.get("Full Name"),
                            "phone": r.get("Phone"),
                        })
                if leads:
                    return leads
            except Exception as e:
                log.warning("Could not read leads from Google Sheets: %s. Using local database backup.", e)

        # Fallback to local DB leads
        from app.database.database import SessionLocal
        from app.database.models import CustomerLead
        db = SessionLocal()
        try:
            db_leads = db.query(CustomerLead).filter(CustomerLead.is_subscribed == True).all()
            return [{"email": l.email, "name": l.full_name, "phone": l.phone} for l in db_leads]
        finally:
            db.close()
