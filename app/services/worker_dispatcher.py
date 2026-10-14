"""
Fulfillment Outbox Worker Dispatcher:
Decouples physical printing, Google Sheets sync, and notifications.
Processes tasks independently with retry backoff and error logging.
"""
from datetime import datetime
from typing import Dict, Any

from app.database.database import SessionLocal
from app.database.models import FulfillmentJob, Order
from app.services.printer_service import PrinterService
from app.services.sheets_service import SheetsService
from app.services.notification_service import NotificationService
from app.utils.logger import get_logger

log = get_logger(__name__)


class WorkerDispatcher:

    @classmethod
    def dispatch_pending_jobs(cls) -> Dict[str, int]:
        """
        Polls and executes pending fulfillment jobs from the outbox table.
        Independent execution ensures a printer offline error never breaks Sheets sync or notifications.
        """
        db = SessionLocal()
        summary = {"processed": 0, "succeeded": 0, "failed": 0}
        try:
            jobs = (
                db.query(FulfillmentJob)
                .filter(FulfillmentJob.status.in_(["PENDING", "FAILED"]))
                .filter(FulfillmentJob.retry_count < FulfillmentJob.max_retries)
                .all()
            )

            for job in jobs:
                summary["processed"] += 1
                job.status = "PROCESSING"
                db.commit()

                order = db.query(Order).filter(Order.id == job.order_id).first()
                if not order:
                    job.status = "FAILED"
                    job.last_error = f"Order id {job.order_id} not found."
                    db.commit()
                    summary["failed"] += 1
                    continue

                order_dict = order.to_dict()
                ok = False
                err_msg = ""

                try:
                    if job.job_type == "KITCHEN_PRINT":
                        ok, msg = PrinterService.print_order(order_dict)
                        if ok:
                            order.print_status = "PRINTED"
                        else:
                            order.print_status = "FAILED"
                            err_msg = msg

                    elif job.job_type == "GSHEETS_SYNC":
                        ok, msg = SheetsService.sync_order_to_google_sheets(order_dict)
                        if ok:
                            order.sheets_sync_status = "SYNCED"
                        else:
                            order.sheets_sync_status = "FAILED"
                            err_msg = msg

                    elif job.job_type == "CUSTOMER_NOTIFY":
                        ok = NotificationService.notify_order_confirmed(order_dict)
                        if not ok:
                            err_msg = "Could not deliver push notification"

                    else:
                        ok = False
                        err_msg = f"Unknown job type: {job.job_type}"

                except Exception as e:
                    ok = False
                    err_msg = str(e)
                    log.exception("Worker error processing job %d (%s): %s", job.id, job.job_type, e)

                if ok:
                    job.status = "SUCCESS"
                    job.updated_at = datetime.utcnow()
                    summary["succeeded"] += 1
                else:
                    job.status = "FAILED"
                    job.retry_count += 1
                    job.last_error = err_msg
                    job.updated_at = datetime.utcnow()
                    summary["failed"] += 1

                db.commit()

            return summary
        finally:
            db.close()
