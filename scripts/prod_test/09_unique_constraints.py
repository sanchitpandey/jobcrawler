import sqlite3
con = sqlite3.connect("jobcrawler.db")
checks = [
    ("users", "email"),
    ("subscriptions", "razorpay_payment_id"),
    ("webhook_events", "event_id"),
]
for tbl, col in checks:
    idx = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?",
        (tbl,),
    ).fetchall()
    unique_idx = [(n, s) for n, s in idx if s and "UNIQUE" in s.upper() and col in s]
    # Also check column-level UNIQUE in CREATE TABLE
    create = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
    ).fetchone()
    inline_unique = create and "UNIQUE" in create[0].upper() and col in create[0]
    has = bool(unique_idx) or inline_unique
    print(f"{tbl}.{col}: {'UNIQUE' if has else 'NOT UNIQUE'} (idx={len(unique_idx)}, inline={inline_unique})")
print()
for tbl in ["subscriptions", "webhook_events"]:
    r = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
    ).fetchone()
    print(f"--- {tbl} CREATE TABLE ---")
    print(r[0] if r else "(missing)")
    print()
con.close()
