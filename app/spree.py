"""Read-only Spree 6 adapter. The configured secret key selects the live store."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import httpx
from .errors import AppError


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Spree:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def _get(self, path, params=None):
        # Only GET; paths are chosen in code, never by the model. No credential redirects.
        for attempt in range(2):
            try:
                with httpx.Client(base_url=self.settings.spree_url, timeout=15, transport=self.transport,
                                  trust_env=False, follow_redirects=False) as client:
                    response = client.get("/api/v3/admin/" + path, params=params,
                                          headers={"X-Spree-Api-Key": self.settings.spree_key})
                if response.status_code in {502, 503, 504} and attempt == 0:
                    continue
                if response.status_code in {401, 403}:
                    raise AppError("spree_access_denied", "Spree rejected the key or its read permissions.", 403)
                if response.status_code == 404:
                    raise AppError("order_not_found", "No matching record in the configured store.", 404)
                response.raise_for_status()
                return response.json()
            except httpx.TransportError:
                if attempt == 0:
                    continue
                raise AppError("spree_unavailable", "Spree is unavailable. Start the store and try again.", 503)
            except (httpx.HTTPStatusError, ValueError):
                raise AppError("spree_invalid_response", "Spree returned an unexpected response.", 502)

    def get_order(self, reference):
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", reference):
            raise AppError("invalid_reference", "Use an exact order number or order ID, without spaces or URLs.")
        if self.settings.mode == "fixture":
            fixture = json.loads((Path(__file__).resolve().parents[1] / "examples/store.json").read_text(encoding="utf-8"))
            matches = [order for order in fixture["orders"] if reference in {order["id"], order["number"]}
                       and order["store_id"] == self.settings.store_id]
        elif reference.startswith("or_"):
            matches = [self._get("orders/" + quote(reference, safe=""), {"expand": "items.variant,fulfillments"})]
        else:
            result = self._get("orders", {"q[number_eq]": reference, "limit": 100})
            # Spree can ignore unsupported filters: verify every match ourselves.
            matches = [record for record in result.get("data", []) if record.get("number") == reference]
            if result.get("meta", {}).get("next") and not matches:
                raise AppError("lookup_incomplete", "Search pagination prevents an exact match. Use the Spree order ID.")
            if len(matches) == 1:
                matches = [self._get("orders/" + quote(matches[0]["id"], safe=""), {"expand": "items.variant,fulfillments"})]
        if not matches:
            raise AppError("order_not_found", "No matching order in the configured store.", 404)
        if len(matches) != 1:
            raise AppError("order_ambiguous", "Multiple exact orders matched; use the Spree order ID.", 409)
        raw = matches[0]
        if raw.get("store_id") and str(raw["store_id"]) != self.settings.store_id:
            raise AppError("store_denied", "This record is outside the configured store.", 403)
        if not isinstance(raw.get("items"), list):
            raise AppError("spree_schema", "Order items were not expanded. Check permissions and Spree version.", 502)
        return {"id": raw["id"], "number": raw["number"], "store_id": self.settings.store_id,
                "status": raw.get("status"), "payment_status": raw.get("payment_status"),
                "fulfillment_status": raw.get("fulfillment_status"), "currency": raw.get("currency"),
                "total": raw.get("total"), "items": [self._item(item) for item in raw["items"]],
                "fulfillments": [{key: item.get(key) for key in ("id", "number", "status", "tracking", "shipped_at", "delivered_at")}
                                 for item in raw.get("fulfillments", []) if isinstance(item, dict)],
                "source": self.settings.mode, "retrieved_at": utc_now()}

    @staticmethod
    def _item(item):
        variant = item.get("variant") if isinstance(item.get("variant"), dict) else {}
        return {"sku": item.get("sku") or variant.get("sku"), "name": item.get("name"),
                "quantity": item.get("quantity"), "unit_price": item.get("price"), "total": item.get("total")}

    def ready(self):
        if self.settings.mode == "fixture":
            return True
        try:
            self._get("orders", {"limit": 1})
            return True
        except AppError:
            return False
