from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from langchain_core.tools import tool


class ShoppingDataStore:
    """Student scaffold for mock-data lookup."""

    def __init__(self, json_path: Path) -> None:
        if not json_path.exists():
            raise FileNotFoundError(f"Mock data file not found: {json_path}")
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.metadata = data.get("metadata", {})
        self.customers_list = data.get("customers", [])
        self.orders_list = data.get("orders", [])
        self.vouchers_list = data.get("vouchers", [])
        
        # Build indexes
        self.customer_by_id = {c["customer_id"]: c for c in self.customers_list}
        self.order_by_id = {o["order_id"]: o for o in self.orders_list}
        
        self.orders_by_customer_id = {}
        for o in self.orders_list:
            cid = o["customer_id"]
            if cid not in self.orders_by_customer_id:
                self.orders_by_customer_id[cid] = []
            self.orders_by_customer_id[cid].append(o)
            
        # Sort orders by created_at descending
        for cid in self.orders_by_customer_id:
            self.orders_by_customer_id[cid].sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
        self.vouchers_by_customer_id = {}
        for v in self.vouchers_list:
            cid = v["customer_id"]
            if cid not in self.vouchers_by_customer_id:
                self.vouchers_by_customer_id[cid] = []
            self.vouchers_by_customer_id[cid].append(v)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        customer = self.customer_by_id.get(customer_id)
        if customer:
            return {"status": "ok", "customer": customer}
        return {"status": "not_found", "customer_id": customer_id}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        orders = self.orders_by_customer_id.get(customer_id, [])
        if orders:
            return {"status": "ok", "orders": orders[:limit]}
        return {"status": "not_found", "customer_id": customer_id}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        order = self.order_by_id.get(order_id)
        if order:
            return {"status": "ok", "order": order}
        return {"status": "not_found", "order_id": order_id}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        vouchers = self.vouchers_by_customer_id.get(customer_id, [])
        if only_active:
            vouchers = [v for v in vouchers if v.get("status") == "active"]
            
        if vouchers or self.customer_by_id.get(customer_id):
            return {"status": "ok", "vouchers": vouchers}
        return {"status": "not_found", "customer_id": customer_id}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_profile(customer_id: str) -> str:
        """Tra cứu thông tin cá nhân, hạng thành viên và địa chỉ của khách hàng."""
        res = store.get_customer_by_id(customer_id)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_customer_orders(customer_id: str) -> str:
        """Tra cứu danh sách các đơn hàng gần đây của một khách hàng."""
        res = store.get_orders_by_customer_id(customer_id)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_order_details(order_id: str) -> str:
        """Tra cứu chi tiết một đơn hàng cụ thể bao gồm trạng thái, ngày giao dự kiến và khả năng đổi trả."""
        res = store.get_order_detail_by_order_id(order_id)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_customer_vouchers(customer_id: str) -> str:
        """Tra cứu danh sách các mã giảm giá (voucher) của khách hàng, bao gồm trạng thái sử dụng."""
        res = store.get_vouchers_by_customer_id(customer_id)
        return json.dumps(res, ensure_ascii=False)

    return [get_customer_profile, get_customer_orders, get_order_details, get_customer_vouchers]
