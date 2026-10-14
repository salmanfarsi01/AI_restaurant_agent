"""
Dedicated Kitchen Thermal POS Printer Service.
Supports Network ESC/POS (TCP 9100), Windows Print Spooler (win32print),
and Resilient Local File/PDF Mock Fallback.
"""
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class PrinterService:

    @staticmethod
    def format_receipt_text(order: Dict[str, Any], is_reprint: bool = False) -> str:
        """Formats 80mm / 48-column thermal receipt string."""
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        reprint_banner = "\n*** DUPLICATE / REPRINT ***\n" if is_reprint else ""
        
        lines = [
            "=" * 48,
            f"{settings.restaurant_name:^48}",
            f"{settings.restaurant_address:^48}",
            f"Tel: {settings.restaurant_phone:^43}",
            "=" * 48,
            reprint_banner,
            f"ORDER CODE : {order.get('order_code', 'UNKNOWN')}",
            f"DATE/TIME  : {order.get('created_at', now_str)}",
            f"STATUS     : CONFIRMED (EMAIL VERIFIED)",
            f"PAYMENT    : CASH ON DELIVERY (PENDING)",
            "-" * 48,
            "CUSTOMER DETAILS:",
            f"Name    : {order.get('customer_name', '')}",
            f"Phone   : {order.get('customer_phone', '')}",
            f"Email   : {order.get('customer_email', '')}",
            f"Address : {order.get('delivery_address', '')}",
        ]

        if order.get("special_notes"):
            lines.append(f"Notes   : {order.get('special_notes')}")

        lines.extend([
            "-" * 48,
            f"{'QTY':<5} {'ITEM DESCRIPTION':<25} {'PRICE':>7} {'TOTAL':>8}",
            "-" * 48,
        ])

        for item in order.get("items", []):
            qty = str(item.get("quantity", 1))
            name = item.get("item_name", "")[:24]
            unit = f"{item.get('unit_price', 0.0):.2f}"
            total = f"{item.get('line_total', 0.0):.2f}"
            lines.append(f"{qty:<5} {name:<25} {unit:>7} {total:>8}")

        subtotal = f"৳{order.get('subtotal', 0.0):.2f}"
        delivery_fee = f"৳{order.get('delivery_fee', 60.0):.2f}"
        grand_total = f"৳{order.get('total_amount', 0.0):.2f}"

        lines.extend([
            "-" * 48,
            f"{'SUBTOTAL:':<35} {subtotal:>12}",
            f"{'DELIVERY FEE:':<35} {delivery_fee:>12}",
            "=" * 48,
            f"{'GRAND TOTAL (TO COLLECT):':<35} {grand_total:>12}",
            "=" * 48,
            f"{'KITCHEN FULFILLMENT TICKET':^48}",
            "=" * 48,
            "\n\n\n",  # Feed paper
        ])

        return "\n".join(lines)

    @staticmethod
    def print_to_network(receipt_text: str) -> Tuple[bool, str]:
        """Sends raw ESC/POS byte commands to network thermal printer on TCP port 9100."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(4.0)
            s.connect((settings.printer_ip, settings.printer_port))

            # ESC @ (initialize) + text + GS V 1 (cut paper)
            init_cmd = b"\x1b\x40"
            cut_cmd = b"\x1d\x56\x01"
            payload = init_cmd + receipt_text.encode("utf-8", errors="replace") + cut_cmd

            s.sendall(payload)
            s.close()
            log.info("Printed ticket via network printer at %s:%d", settings.printer_ip, settings.printer_port)
            return True, "Printed successfully via network POS."
        except Exception as e:
            log.warning("Network printer error: %s. Using mock fallback.", e)
            return False, str(e)

    @staticmethod
    def print_to_windows_spooler(receipt_text: str) -> Tuple[bool, str]:
        """Prints via Windows win32print raw printer spooler."""
        try:
            import win32print
            p_name = settings.printer_windows_name
            h_printer = win32print.OpenPrinter(p_name)
            try:
                h_job = win32print.StartDocPrinter(h_printer, 1, ("Kitchen Order Ticket", None, "RAW"))
                win32print.StartPagePrinter(h_printer)
                cut_cmd = "\x1d\x56\x01"
                win32print.WritePrinter(h_printer, (receipt_text + cut_cmd).encode("utf-8", errors="replace"))
                win32print.EndPagePrinter(h_printer)
                win32print.EndDocPrinter(h_printer)
                log.info("Printed ticket via Windows spooler '%s'", p_name)
                return True, "Printed successfully via Windows driver."
            finally:
                win32print.ClosePrinter(h_printer)
        except Exception as e:
            log.warning("Windows spooler error: %s. Using mock fallback.", e)
            return False, str(e)

    @staticmethod
    def print_to_file_mock(order: Dict[str, Any], receipt_text: str) -> Tuple[bool, str]:
        """Resilient fallback: writes receipt text directly into data/receipts/."""
        Path(settings.receipts_dir).mkdir(parents=True, exist_ok=True)
        order_code = order.get("order_code", "UNKNOWN")
        file_path = Path(settings.receipts_dir) / f"receipt_{order_code}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(receipt_text)

        log.info("Saved kitchen order receipt to %s", file_path)
        return True, f"Receipt saved to {file_path}"

    @classmethod
    def print_order(cls, order: Dict[str, Any], is_reprint: bool = False) -> Tuple[bool, str]:
        """Dispatches order ticket according to configured printer mode with resilient fallback."""
        receipt_text = cls.format_receipt_text(order, is_reprint=is_reprint)
        mode = settings.printer_mode.lower()

        if mode == "network":
            ok, msg = cls.print_to_network(receipt_text)
            if ok:
                return True, msg

        elif mode == "windows":
            ok, msg = cls.print_to_windows_spooler(receipt_text)
            if ok:
                return True, msg

        # Fallback to local receipt file mock
        return cls.print_to_file_mock(order, receipt_text)
