from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import datetime
import difflib
import pandas as pd
import io
import os

from database import get_db, init_db, get_india_date, VARIANTS, IST
from pdf_parser import parse_pdf_receipt

app = FastAPI(title="Wine Shop Manager API")

@app.get("/")
async def root():
    return {"status": "online", "message": "Wine Shop API is running"}

@app.get("/health")
async def health_check(conn=Depends(get_db)):
    try:
        # Test a simple query
        conn.execute("SELECT 1").fetchone()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

origins = [
    "http://localhost:3000", 
    "http://127.0.0.1:3000",
    "https://wineshop-frontend.vercel.app" # Default fallback
]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    origins.append(frontend_url.strip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    role: str  # "admin" or "shopkeeper"

class ClosingUpdate(BaseModel):
    date: str
    brand_id: int
    variant: str
    closing: int

class ReceiptUpdate(BaseModel):
    date: str
    brand_id: int
    variant: str
    qty: int

class BrandCreate(BaseModel):
    name: str

class PriceUpdate(BaseModel):
    prices: dict  # {variant: price}

class PasswordChange(BaseModel):
    username: str
    new_password: str

class PinChange(BaseModel):
    new_pin: str

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────

@app.post("/api/login")
def login(req: LoginRequest):
    conn = get_db()
    try:
        if req.role == "shopkeeper":
            row = conn.execute(
                "SELECT password FROM users WHERE username='shopkeeper'"
            ).fetchone()
            if row and row["password"] == req.password:
                return {"success": True, "role": "shopkeeper"}
        else:
            row = conn.execute(
                "SELECT password, role FROM users WHERE username=?", (req.username,)
            ).fetchone()
            if row and row["password"] == req.password:
                return {"success": True, "role": row["role"], "username": req.username}
        raise HTTPException(status_code=401, detail="Invalid credentials")
    finally:
        conn.close()

# ─────────────────────────────────────────────
# BRANDS
# ─────────────────────────────────────────────

@app.get("/api/brands")
def get_brands():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.post("/api/brands")
def add_brand(brand: BrandCreate):
    conn = get_db()
    try:
        clean_name = " ".join(brand.name.split()).title()
        search_key = clean_name.lower().replace(" ", "")
        existing = conn.execute(
            "SELECT name FROM brands WHERE LOWER(REPLACE(name, ' ', '')) = ?",
            (search_key,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Duplicate brand: '{existing['name']}'")
        cur = conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?) RETURNING id", (clean_name, True))
        bid = cur.fetchone()["id"]
        for v in VARIANTS:
            conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))
        conn.commit()
        return {"id": bid, "name": clean_name}
    finally:
        conn.close()

# ─────────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────────

@app.get("/api/inventory/{date_str}")
def get_inventory(date_str: str):
    conn = get_db()
    try:
        query = """
        SELECT b.name, i.*,
               COALESCE(
                   (SELECT old_price FROM price_audit
                    WHERE brand_id = i.brand_id AND variant = i.variant AND timestamp > ? || ' 23:59:59'
                    ORDER BY timestamp ASC LIMIT 1),
                   p.price
               ) as price
        FROM inventory i
        JOIN brands b ON i.brand_id = b.id
        LEFT JOIN prices p ON (i.brand_id = p.brand_id AND i.variant = p.variant)
        WHERE i.date = ?
        """
        rows = conn.execute(query, (date_str, date_str)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.post("/api/inventory/init/{date_str}")
def initialize_day(date_str: str):
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT count(*) as cnt FROM inventory WHERE date=?", (date_str,)
        ).fetchone()
        if existing["cnt"] > 0:
            return {"message": "Already initialized"}

        prev_date = (datetime.datetime.strptime(date_str, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()

        for brand in brands:
            for v in VARIANTS:
                res = conn.execute(
                    "SELECT closing FROM inventory WHERE date=? AND brand_id=? AND variant=?",
                    (prev_date, brand["id"], v)
                ).fetchone()
                opening = res["closing"] if res else 0
                conn.execute(
                    "INSERT OR IGNORE INTO inventory (date, brand_id, variant, opening, receipts, closing, status) VALUES (?, ?, ?, ?, 0, 0, 0)",
                    (date_str, brand["id"], v, opening)
                )
        conn.commit()
        return {"message": f"Initialized {date_str}"}
    finally:
        conn.close()

@app.put("/api/inventory/closing")
def update_closing(update: ClosingUpdate):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
            (update.closing, update.date, update.brand_id, update.variant)
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.put("/api/inventory/receipts")
def update_receipts(update: ReceiptUpdate):
    conn = get_db()
    try:
        cur = conn.execute(
            "UPDATE inventory SET receipts=? WHERE date=? AND brand_id=? AND variant=?",
            (update.qty, update.date, update.brand_id, update.variant)
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO inventory (date, brand_id, variant, opening, receipts, closing, status) VALUES (?, ?, ?, 0, ?, 0, 0)",
                (update.date, update.brand_id, update.variant, update.qty)
            )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.post("/api/inventory/submit/{date_str}")
def submit_report(date_str: str):
    conn = get_db()
    try:
        conn.execute("UPDATE inventory SET status=1 WHERE date=?", (date_str,))
        conn.commit()
        return {"message": "Report submitted"}
    finally:
        conn.close()

@app.post("/api/inventory/approve/{date_str}")
def approve_report(date_str: str):
    conn = get_db()
    try:
        conn.execute("UPDATE inventory SET status=2 WHERE date=?", (date_str,))
        conn.commit()
        return {"message": "Report approved and locked"}
    finally:
        conn.close()

@app.post("/api/inventory/reject/{date_str}")
def reject_report(date_str: str):
    conn = get_db()
    try:
        conn.execute("UPDATE inventory SET status=0 WHERE date=?", (date_str,))
        conn.commit()
        return {"message": "Report rejected"}
    finally:
        conn.close()

# ─────────────────────────────────────────────
# PRICES
# ─────────────────────────────────────────────

@app.get("/api/prices/{brand_id}")
def get_prices(brand_id: int):
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM prices WHERE brand_id=?", (brand_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.put("/api/prices/{brand_id}")
def update_prices(brand_id: int, update: PriceUpdate):
    conn = get_db()
    try:
        now_str = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        for var, new_price in update.prices.items():
            res = conn.execute("SELECT price FROM prices WHERE brand_id=? AND variant=?", (brand_id, var)).fetchone()
            old_price = res["price"] if (res and res["price"] is not None) else 0.0
            if float(new_price) != float(old_price):
                conn.execute("UPDATE prices SET price=? WHERE brand_id=? AND variant=?", (new_price, brand_id, var))
                conn.execute(
                    "INSERT INTO price_audit (timestamp, brand_id, variant, old_price, new_price) VALUES (?, ?, ?, ?, ?)",
                    (now_str, brand_id, var, old_price, new_price)
                )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.get("/api/price-audit")
def get_price_audit():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT pa.timestamp, b.name as brand, pa.variant, pa.old_price, pa.new_price
            FROM price_audit pa
            JOIN brands b ON pa.brand_id = b.id
            ORDER BY pa.timestamp DESC LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# ─────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────

def build_daily_report(conn, date_str: str):
    query = """
        SELECT b.name, i.variant, i.opening, i.receipts, i.closing,
               COALESCE(
                   (SELECT old_price FROM price_audit
                    WHERE brand_id = i.brand_id AND variant = i.variant AND timestamp > ? || ' 23:59:59'
                    ORDER BY timestamp ASC LIMIT 1),
                   p.price
               ) as price
        FROM inventory i
        JOIN brands b ON i.brand_id = b.id
        LEFT JOIN prices p ON i.brand_id = p.brand_id AND i.variant = p.variant
        WHERE i.date = ?
    """
    df = pd.read_sql_query(query, conn, params=(date_str, date_str))
    if df.empty:
        return None
    df["available"] = df["opening"] + df["receipts"]
    df["sold"] = df["available"] - df["closing"]
    df["revenue"] = df["sold"] * df["price"]
    return df

@app.get("/api/reports/daily/{date_str}")
def get_daily_report(date_str: str):
    conn = get_db()
    try:
        df = build_daily_report(conn, date_str)
        if df is None:
            return {"data": [], "total_revenue": 0}

        result = []
        for name, group in df.groupby("name"):
            row = {"brand": name}
            for _, r in group.iterrows():
                v = r["variant"]
                row[f"{v}_available"] = int(r["available"])
                row[f"{v}_closing"] = int(r["closing"])
                row[f"{v}_sold"] = int(r["sold"])
            row["revenue"] = float(group["revenue"].sum())
            result.append(row)

        total_rev = float(df["revenue"].sum())
        return {"data": result, "total_revenue": total_rev}
    finally:
        conn.close()

@app.get("/api/reports/trend")
def get_trend():
    conn = get_db()
    try:
        end_d = get_india_date()
        start_d = end_d - datetime.timedelta(days=6)
        query = """
            SELECT i.date,
                   ((i.opening + i.receipts) - i.closing) as sold,
                   COALESCE(
                       (SELECT old_price FROM price_audit
                        WHERE brand_id = i.brand_id AND variant = i.variant AND timestamp > i.date || ' 23:59:59'
                        ORDER BY timestamp ASC LIMIT 1),
                       p.price
                   ) as price
            FROM inventory i
            JOIN brands b ON i.brand_id = b.id
            LEFT JOIN prices p ON i.brand_id = p.brand_id AND i.variant = p.variant
            WHERE i.date >= ? AND i.date <= ?
        """
        df = pd.read_sql_query(query, conn, params=(start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d")))
        if df.empty:
            return []
        df["revenue"] = df["sold"] * df["price"]
        daily = df.groupby("date")["revenue"].sum().reset_index()
        return daily.to_dict("records")
    finally:
        conn.close()

@app.get("/api/reports/excel")
def get_excel_report(start_date: str, end_date: str):
    conn = get_db()
    try:
        start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
        delta = (end - start).days + 1
        date_list = [start + datetime.timedelta(days=i) for i in range(delta)]

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            days_written = 0
            for d in date_list:
                d_str = d.strftime("%Y-%m-%d")
                df = build_daily_report(conn, d_str)
                if df is not None:
                    variants_order = ["2L", "1L", "Q", "P", "N"]
                    def make_pivot(val_col):
                        p = df.pivot_table(index="name", columns="variant", values=val_col, aggfunc="sum").fillna(0)
                        for v in variants_order:
                            if v not in p.columns: p[v] = 0
                        return p[variants_order]
                    p_open = make_pivot("available")
                    p_close = make_pivot("closing")
                    p_sold = make_pivot("sold")
                    rev_series = df.groupby("name")["revenue"].sum()
                    p_open.columns = pd.MultiIndex.from_product([["1. Opening"], p_open.columns])
                    p_close.columns = pd.MultiIndex.from_product([["2. Closing"], p_close.columns])
                    p_sold.columns = pd.MultiIndex.from_product([["3. Sales"], p_sold.columns])
                    final_df = pd.concat([p_open, p_close, p_sold], axis=1)
                    final_df[("3. Sales", "Revenue (₹)")] = rev_series
                    final_df = final_df.fillna(0)
                    totals = final_df.sum(numeric_only=True)
                    final_df.loc["TOTAL"] = totals
                    final_df.to_excel(writer, sheet_name=d.strftime("%b %d"))
                    days_written += 1
            if days_written == 0:
                pd.DataFrame({"Message": ["No Data Found"]}).to_excel(writer, sheet_name="No Data")

        output.seek(0)
        filename = f"Sales_Report_{start_date}_to_{end_date}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    finally:
        conn.close()

# ─────────────────────────────────────────────
# APPROVALS
# ─────────────────────────────────────────────

@app.get("/api/pending-approvals")
def get_pending_approvals():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT date FROM inventory WHERE status=1 ORDER BY date DESC"
        ).fetchall()
        return [r["date"] for r in rows]
    finally:
        conn.close()

# ─────────────────────────────────────────────
# STOCK INTAKE — IMPORT
# ─────────────────────────────────────────────

@app.post("/api/import/receipts-excel")
async def import_receipts_excel(date: str, file: UploadFile = File(...)):
    conn = get_db()
    try:
        content = await file.read()
        buf = io.BytesIO(content)
        ext = file.filename.split(".")[-1].lower()
        df_imp = pd.read_csv(buf) if ext == "csv" else pd.read_excel(buf)
        df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()

        variant_map = {
            "2l": "2L", "1l": "1L", "q": "Q", "750ml": "Q",
            "p": "P", "375ml": "P", "n": "N", "180ml": "N"
        }
        found_maps = {c: variant_map[k] for c in df_imp.columns for k in variant_map if k in c}
        if not found_maps:
            raise HTTPException(status_code=400, detail="No size columns found")

        db_brands = conn.execute("SELECT id, name FROM brands").fetchall()
        brand_map = {row["name"].lower().strip(): int(row["id"]) for row in db_brands}

        brand_col = df_imp.columns[0]
        for c in df_imp.columns:
            if "brand" in c or "name" in c:
                brand_col = c
                break

        count = 0
        for _, row in df_imp.iterrows():
            file_brand = str(row[brand_col]).strip()
            bid = brand_map.get(file_brand.lower())
            if bid:
                for col, var in found_maps.items():
                    try:
                        qty = int(float(row[col]))
                    except:
                        qty = 0
                    if qty > 0:
                        cur = conn.execute(
                            "UPDATE inventory SET receipts=receipts+? WHERE date=? AND brand_id=? AND variant=?",
                            (qty, date, bid, var)
                        )
                        if cur.rowcount == 0:
                            conn.execute(
                                "INSERT INTO inventory (date, brand_id, variant, opening, receipts, closing, status) VALUES (?, ?, ?, 0, ?, 0, 0)",
                                (date, bid, var, qty)
                            )
                count += 1
        conn.commit()
        return {"imported": count}
    finally:
        conn.close()

@app.post("/api/import/pdf")
async def import_pdf(file: UploadFile = File(...)):
    conn = get_db()
    try:
        content = await file.read()
        db_brands = conn.execute("SELECT id, name FROM brands").fetchall()
        db_brands_list = sorted([(r["name"], r["id"]) for r in db_brands], key=lambda x: len(x[0]), reverse=True)

        from io import BytesIO
        result = parse_pdf_receipt(BytesIO(content), db_brands_list)
        return {"items": result}
    finally:
        conn.close()

@app.post("/api/import/pdf-save")
async def save_pdf_items(items: List[dict]):
    conn = get_db()
    try:
        for item in items:
            bid = int(item["brand_id"])
            var = item["variant"]
            qty = int(item["qty"])
            cur = conn.execute(
                "UPDATE inventory SET receipts=receipts+? WHERE date=? AND brand_id=? AND variant=?",
                (qty, item["date"], bid, var)
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO inventory (date, brand_id, variant, opening, receipts, closing, status) VALUES (?, ?, ?, 0, ?, 0, 0)",
                    (item["date"], bid, var, qty)
                )
        conn.commit()
        return {"saved": len(items)}
    finally:
        conn.close()

@app.post("/api/import/brands-excel")
async def import_brands_excel(file: UploadFile = File(...)):
    conn = get_db()
    try:
        content = await file.read()
        buf = io.BytesIO(content)
        ext = file.filename.split(".")[-1].lower()
        data_dict = {"Default": pd.read_csv(buf)} if ext == "csv" else pd.read_excel(buf, sheet_name=None)

        existing_brands = conn.execute("SELECT id, name FROM brands").fetchall()
        brand_map_strict = {
            str(r["name"]).lower().replace(" ", ""): int(r["id"])
            for r in existing_brands
        }
        existing_names_list = [r["name"] for r in existing_brands]

        total_touched = 0
        total_prices = 0
        typos_fixed = 0

        for sheet_name, df_imp in data_dict.items():
            if df_imp.empty:
                continue
            df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
            variant_map = {
                "2l": "2L", "1l": "1L", "q": "Q", "750ml": "Q",
                "p": "P", "375ml": "P", "n": "N", "180ml": "N"
            }
            found_maps = {}
            for col in df_imp.columns:
                for key, sys_var in variant_map.items():
                    if key in col:
                        found_maps[col] = sys_var
                        break
            if not found_maps:
                continue

            brand_col = df_imp.columns[0]
            for c in df_imp.columns:
                if "brand" in c or "name" in c:
                    brand_col = c
                    break

            for _, row in df_imp.iterrows():
                raw_brand = str(row[brand_col]).strip()
                if not raw_brand or raw_brand.lower() == "nan":
                    continue

                bid = None
                strict_key = raw_brand.lower().replace(" ", "")
                if strict_key in brand_map_strict:
                    bid = brand_map_strict[strict_key]
                else:
                    matches = difflib.get_close_matches(raw_brand, existing_names_list, n=1, cutoff=0.85)
                    if matches:
                        matched_name = matches[0]
                        matched_key = matched_name.lower().replace(" ", "")
                        bid = brand_map_strict.get(matched_key)
                        typos_fixed += 1
                    else:
                        clean_name = " ".join(raw_brand.split()).title()
                        cur = conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?) RETURNING id", (clean_name, True))
                        bid = cur.fetchone()["id"]
                        brand_map_strict[clean_name.lower().replace(" ", "")] = bid
                        existing_names_list.append(clean_name)
                        for v in VARIANTS:
                            conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))

                total_touched += 1
                now_str = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                for col_name, sys_var in found_maps.items():
                    val = row[col_name]
                    try:
                        if pd.isna(val) or str(val).strip() == "":
                            continue
                        new_price = float(val)
                        if new_price >= 0:
                            res = conn.execute("SELECT price FROM prices WHERE brand_id=? AND variant=?", (bid, sys_var)).fetchone()
                            old_price = res["price"] if (res and res["price"] is not None) else 0.0
                            if new_price != old_price:
                                conn.execute("UPDATE prices SET price=? WHERE brand_id=? AND variant=?", (new_price, bid, sys_var))
                                conn.execute(
                                    "INSERT INTO price_audit (timestamp, brand_id, variant, old_price, new_price) VALUES (?, ?, ?, ?, ?)",
                                    (now_str, bid, sys_var, old_price, new_price)
                                )
                                total_prices += 1
                    except:
                        continue

        conn.commit()
        return {"brands_processed": total_touched, "prices_updated": total_prices, "typos_fixed": typos_fixed}
    finally:
        conn.close()

@app.post("/api/import/closing-excel")
async def import_closing_excel(date: str, file: UploadFile = File(...)):
    conn = get_db()
    try:
        content = await file.read()
        buf = io.BytesIO(content)
        ext = file.filename.split(".")[-1].lower()
        if ext == "csv":
            data_dict = {"Default": pd.read_csv(buf)}
        else:
            data_dict = pd.read_excel(buf, sheet_name=None)

        variant_map = {
            "2l": "2L", "2000ml": "2L", "1l": "1L", "1000ml": "1L", "full": "1L",
            "q": "Q", "750ml": "Q", "qt": "Q", "quart": "Q",
            "p": "P", "375ml": "P", "pint": "P", "half": "P",
            "n": "N", "180ml": "N", "nip": "N", "quarter": "N"
        }

        db_brands = conn.execute("SELECT id, name FROM brands").fetchall()
        brand_map = {r["name"].lower().strip(): int(r["id"]) for r in db_brands}

        match_count = 0
        for sheet_name, df_imp in data_dict.items():
            if df_imp.empty:
                continue
            df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
            found_maps = {}
            for col in df_imp.columns:
                for key, sys_var in variant_map.items():
                    if key in col:
                        found_maps[col] = sys_var
                        break

            brand_col = df_imp.columns[0]
            for c in df_imp.columns:
                if "brand" in c or "name" in c or "item" in c:
                    brand_col = c
                    break

            for _, row in df_imp.iterrows():
                file_brand = str(row[brand_col]).strip()
                bid = brand_map.get(file_brand.lower())
                if bid:
                    for col_name, sys_var in found_maps.items():
                        try:
                            val = row[col_name]
                            closing_qty = int(float(val))
                        except:
                            closing_qty = 0
                        conn.execute(
                            "UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
                            (closing_qty, date, bid, sys_var)
                        )
                    match_count += 1
        conn.commit()
        return {"imported": match_count}
    finally:
        conn.close()

# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────

@app.put("/api/settings/password")
def change_password(req: PasswordChange):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET password=? WHERE username=?", (req.new_password, req.username))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.put("/api/settings/pin")
def change_pin(req: PinChange):
    conn = get_db()
    try:
        conn.execute("UPDATE users SET password=? WHERE username='shopkeeper'", (req.new_pin,))
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.get("/api/settings/backup")
def backup_db():
    # Backup is not supported for remote PostgreSQL this way.
    # You should use Supabase dashboard or pg_dump.
    raise HTTPException(status_code=501, detail="Backup not implemented for remote database. Use Supabase dashboard.")

@app.delete("/api/settings/reset-inventory")
def reset_inventory():
    conn = get_db()
    try:
        conn.execute("DELETE FROM inventory")
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.delete("/api/settings/reset-all")
def reset_all():
    conn = get_db()
    try:
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM prices")
        conn.execute("DELETE FROM brands")
        conn.commit()
        return {"success": True}
    finally:
        conn.close()

@app.get("/api/today")
def get_today():
    return {"date": get_india_date().strftime("%Y-%m-%d")}
