"""
Marketing & Staff Administration API:
- POST /api/marketing/broadcast (and alias /api/marketing/campaigns/send)
- POST /api/marketing/broadcast/preview
- GET /api/marketing/unsubscribe
- POST /api/orders/{order_code}/reprint (Staff Kitchen Duplicate Ticket Control)
"""
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Query, Body, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional, Dict, Any

from app.config import settings
from app.database.database import SessionLocal
from app.database.models import CustomerLead, Order
from app.services.marketing_service import MarketingService
from app.services.printer_service import PrinterService
from app.utils.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Marketing & Administration"])


def verify_admin_key(x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-Api-Key")):
    """Validates admin authorization header."""
    if not x_admin_api_key or x_admin_api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin API key.")
    return True


@router.post("/marketing/broadcast")
@router.post("/marketing/campaigns/send")
async def broadcast_campaign(
    payload: Dict[str, Any] = Body(...),
    _auth: bool = Depends(verify_admin_key),
):
    """Broadcasts discount or announcement email to all customer leads in Google Sheets / CRM."""
    result = await MarketingService.broadcast_campaign(payload)
    return JSONResponse({
        "status": "success",
        "message": f"Broadcast dispatched to {result['sent']} customers.",
        "details": result,
    })


@router.post("/marketing/broadcast/preview", response_class=HTMLResponse)
def preview_campaign(
    payload: Dict[str, Any] = Body(...),
    _auth: bool = Depends(verify_admin_key),
):
    """Renders HTML preview of promotional campaign email."""
    html = MarketingService.render_campaign_preview(payload)
    return HTMLResponse(html)


@router.get("/marketing/unsubscribe", response_class=HTMLResponse)
def unsubscribe_customer(email: str = Query(...)):
    """One-click unsubscribe endpoint for customer compliance."""
    db = SessionLocal()
    try:
        lead = db.query(CustomerLead).filter(CustomerLead.email == email.lower()).first()
        if lead:
            lead.is_subscribed = False
            lead.unsubscribed_at = datetime.utcnow()
            db.commit()
            log.info("Customer %s unsubscribed from marketing.", email)

        return HTMLResponse(
            "<h3>Unsubscribed</h3><p>You have been successfully removed from our promotional email list.</p>"
        )
    finally:
        db.close()


@router.post("/orders/{order_code}/reprint")
def reprint_kitchen_ticket(
    order_code: str,
    _auth: bool = Depends(verify_admin_key),
):
    """Staff Kitchen Control: reprints a duplicate receipt clearly marked *** DUPLICATE / REPRINT ***."""
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.order_code == order_code).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order code not found.")

        ok, msg = PrinterService.print_order(order.to_dict(), is_reprint=True)
        order.print_status = "REPRINTED"
        db.commit()
        return {"status": "success", "message": msg, "order_code": order_code}
    finally:
        db.close()
