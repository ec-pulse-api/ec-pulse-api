import os
from datetime import datetime, timezone

import psycopg
import stripe

from app.services.monitor_store import _db_url

PLANS = {"pro": "STRIPE_PRICE_PRO", "business": "STRIPE_PRICE_BUSINESS"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS billing_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_billing_events_created ON billing_events (created_at DESC);
"""


def _init_billing(conn):
    conn.execute(SCHEMA)
    conn.execute("ALTER TABLE api_accounts ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT")
    conn.execute("ALTER TABLE api_accounts ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT")
    conn.execute("ALTER TABLE api_accounts ADD COLUMN IF NOT EXISTS subscription_status TEXT")
    conn.execute("ALTER TABLE api_accounts ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMPTZ")
    conn.execute("ALTER TABLE api_accounts ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_accounts_stripe_customer ON api_accounts (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_accounts_stripe_subscription ON api_accounts (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL")
    conn.commit()


def _stripe():
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    stripe.api_key = key
    return stripe


def _ts(value):
    return datetime.fromtimestamp(value, tz=timezone.utc) if value else None


def _price_plan(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for plan, env_name in PLANS.items():
        if price_id == os.getenv(env_name):
            return plan
    return None


def _account_by_customer(conn, customer_id: str):
    return conn.execute("SELECT api_key_hash FROM api_accounts WHERE stripe_customer_id = %s", (customer_id,)).fetchone()


def _apply_subscription(conn, subscription):
    customer_id = subscription.get("customer")
    subscription_id = subscription.get("id")
    status = subscription.get("status")
    items = subscription.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id") if items else None
    plan = _price_plan(price_id)
    row = _account_by_customer(conn, customer_id) if customer_id else None
    if not row:
        return False
    values = (subscription_id, status, _ts(subscription.get("current_period_start")), _ts(subscription.get("current_period_end")), datetime.now(timezone.utc), row[0])
    if plan:
        conn.execute("""UPDATE api_accounts SET plan=%s, stripe_subscription_id=%s, subscription_status=%s,
            current_period_start=%s, current_period_end=%s, updated_at=%s WHERE api_key_hash=%s""", (plan, *values))
    else:
        conn.execute("""UPDATE api_accounts SET stripe_subscription_id=%s, subscription_status=%s,
            current_period_start=%s, current_period_end=%s, updated_at=%s WHERE api_key_hash=%s""", values)
    return True


def process_webhook(payload: bytes, signature: str) -> dict:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    sdk = _stripe()
    event = sdk.Webhook.construct_event(payload, signature, secret)
    event_data = event.to_dict_recursive()
    event_id = event_data["id"]
    event_type = event_data["type"]
    now = datetime.now(timezone.utc)
    with psycopg.connect(_db_url()) as conn:
        _init_billing(conn)
        inserted = conn.execute("""INSERT INTO billing_events (event_id,event_type,created_at,processed_at,payload)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING RETURNING event_id""",
            (event_id, event_type, _ts(event_data.get("created")) or now, now, event_data)).fetchone()
        if not inserted:
            return {"ok": True, "duplicate": True, "event_id": event_id}
        obj = event_data.get("data", {}).get("object", {})
        handled = False
        if event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            handled = _apply_subscription(conn, obj)
            if event_type == "customer.subscription.deleted" and handled:
                conn.execute("UPDATE api_accounts SET plan='free', subscription_status='canceled', updated_at=%s WHERE stripe_subscription_id=%s", (now, obj.get("id")))
        elif event_type == "checkout.session.completed":
            customer_id = obj.get("customer")
            api_key_hash = (obj.get("metadata") or {}).get("api_key_hash")
            if customer_id and api_key_hash:
                conn.execute("UPDATE api_accounts SET stripe_customer_id=%s, updated_at=%s WHERE api_key_hash=%s", (customer_id, now, api_key_hash))
                handled = True
        conn.commit()
    return {"ok": True, "duplicate": False, "event_id": event_id, "type": event_type, "handled": handled}


def create_checkout(api_key: str, plan: str) -> str:
    if plan not in PLANS:
        raise ValueError("plan must be pro or business")
    price_id = os.getenv(PLANS[plan])
    base_url = os.getenv("APP_BASE_URL")
    if not price_id or not base_url:
        raise RuntimeError("Stripe price and APP_BASE_URL are not configured")
    from app.services.monitor_store import _account_hash
    with psycopg.connect(_db_url()) as conn:
        _init_billing(conn)
        row = conn.execute("SELECT stripe_customer_id FROM api_accounts WHERE api_key_hash=%s", (_account_hash(api_key),)).fetchone()
    customer_id = row[0] if row else None
    params = {"mode": "subscription", "line_items": [{"price": price_id, "quantity": 1}], "success_url": f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}", "cancel_url": f"{base_url}/billing/cancel", "metadata": {"api_key_hash": _account_hash(api_key), "plan": plan}}
    if customer_id:
        params["customer"] = customer_id
    session = _stripe().checkout.Session.create(**params)
    return session.url
