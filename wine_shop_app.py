# --- STANDARD IMPORTS ---
import streamlit as st
import pandas as pd
import sqlite3
import datetime
import os
import pdfplumber

# --- PDF PARSING HELPER ---
def parse_pdf_receipt(uploaded_file, db_brands_list):
    """
    Extracts inventory data from the specific PDF format provided.
    Returns a DataFrame with columns: ['brand_id', 'variant', 'qty']
    """
    extracted_data = []
    
    # 1. Conversion Logic (Cases -> Bottles)
    # Map Size (ml) -> Bottles per Case
    case_conversion = {
        1000: 9, 2000: 9, 
        750: 12, 650: 12, # Assuming 650ml beers are 12/case
        375: 24, 
        180: 48
    }
    
    # Map Size (ml) -> App Variant Code
    size_to_variant = {
        2000: "2L", 1000: "1L", 
        750: "Q", 650: "Q", # Map Beer 650 to Q (closest match for size category)
        375: "P", 
        180: "N"
    }

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            # Extract table. pdfplumber is good at finding grid lines.
            tables = page.extract_tables()
            
            for table in tables:
                # We need to find the specific inventory table.
                # Heuristic: Look for header row containing "Brand Name" and "Size"
                header_idx = -1
                for i, row in enumerate(table):
                    # Clean row to simple text for checking
                    row_text = [str(x).lower().replace('\n', ' ') for x in row if x]
                    if any("brand name" in x for x in row_text) and any("size" in x for x in row_text):
                        header_idx = i
                        break
                
                if header_idx != -1:
                    # Found the table! Process rows below header.
                    # Column Mapping (based on standard layout in your PDF):
                    # Usually: [SlNo, BrandNum, BrandName, Type, Size, QtyCases, ...]
                    # We need to be dynamic to find the indices
                    headers = [str(x).lower().replace('\n', ' ') for x in table[header_idx] if x]
                    
                    # Find indices (safeguard against shifting columns)
                    try:
                        col_brand = next(i for i, h in enumerate(headers) if "brand name" in h)
                        col_size  = next(i for i, h in enumerate(headers) if "size" in h)
                        # Qty Cases is usually "Qty (Cases...)"
                        col_cases = next(i for i, h in enumerate(headers) if "cases" in h)
                        # Sometimes there is a separate "Bottles" column for loose bottles
                        col_btls  = next((i for i, h in enumerate(headers) if "bottles" in h and "cases" not in h), None)
                    except StopIteration:
                        continue # Header found but columns confusing, skip table

                    # Process Data Rows
                    for row in table[header_idx+1:]:
                        if not row or len(row) < 3: continue
                        
                        # Extract Raw Data
                        raw_brand = str(row[col_brand]).strip()
                        raw_size  = str(row[col_size]).strip()
                        raw_cases = str(row[col_cases]).strip()
                        
                        # Skip total rows or garbage
                        if "total" in raw_brand.lower(): continue
                        
                        # 1. Parse Size
                        try:
                            size_ml = int(''.join(filter(str.isdigit, raw_size)))
                        except:
                            continue # Skip if no valid size

                        # 2. Parse Qty
                        # Clean numbers (sometimes "1" comes as "1.00" or with spaces)
                        try:
                            cases = float(raw_cases.split('/')[0]) # Handle "1/0" formats if any
                        except:
                            cases = 0
                            
                        loose_bottles = 0
                        if col_btls is not None and len(row) > col_btls:
                             try:
                                 loose_bottles = float(str(row[col_btls]).split('/')[0])
                             except:
                                 loose_bottles = 0

                        # CALCULATION: Total Bottles = (Cases * Factor) + Loose
                        factor = case_conversion.get(size_ml, 12) # Default to 12 if unknown
                        total_qty = int((cases * factor) + loose_bottles)
                        
                        if total_qty <= 0: continue

                        # 3. Match Brand Name (Fuzzy Match)
                        # We look for the DB Brand Name INSIDE the PDF string.
                        # e.g. DB="Vat 69", PDF="VAT 69 BLENDED SCOTCH..." -> Match!
                        matched_id = None
                        matched_name = None
                        
                        # Sort DB brands by length desc so "Royal Stag Reserve" matches before "Royal Stag"
                        # (This helps specificity, though strict "in" check usually works)
                        for db_name, db_id in db_brands_list:
                            if db_name.lower() in raw_brand.lower():
                                matched_id = db_id
                                matched_name = db_name
                                break
                        
                        if matched_id:
                            variant_code = size_to_variant.get(size_ml)
                            if variant_code:
                                extracted_data.append({
                                    "brand_id": matched_id,
                                    "brand_name": matched_name,
                                    "variant": variant_code,
                                    "qty": total_qty,
                                    "raw_pdf_brand": raw_brand # For debugging
                                })
    
    return pd.DataFrame(extracted_data)

# --- CONFIGURATION & CONSTANTS ---
DB_FILE = "wineshop.db"
VARIANTS = ["2L", "1L", "Q", "P", "N"] # Q=750ml, P=375ml, N=180ml
# Initial 64 Brands from your list (Truncated for brevity, but structure is ready)
INITIAL_BRANDS = [
    "100 Pipers", "Teachers", "Black Dog", "Vat 69", "Antiquity", "Signature", 
    "Royal Challenge", "Blenders Pride", "Royal Stag", "McDowell's (MCW)", 
    "Imperial Blue (IB)", "8PM", "Royal Green", "Bagpiper", "Officer's Choice (OCW)",
    "Old Monk", "Magic Moments", "Smirnoff", "Kingfisher Strong", "Kingfisher Lager", 
    "Budweiser", "Thums Up", "Coca Cola", "Water 1L"
]

# --- DATABASE MANAGEMENT ---
# --- TEMPORARY FIX: DELETE OLD DB ---
##if os.path.exists("wineshop.db"):
##    os.remove("wineshop.db")
# ------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Existing Tables
    c.execute('''CREATE TABLE IF NOT EXISTS brands 
                 (id INTEGER PRIMARY KEY, name TEXT UNIQUE, is_alcohol BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS prices 
                 (brand_id INTEGER, variant TEXT, price REAL, UNIQUE(brand_id, variant))''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (date TEXT, brand_id INTEGER, variant TEXT, 
                  opening INTEGER, receipts INTEGER, closing INTEGER, 
                  status INTEGER, UNIQUE(date, brand_id, variant))''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT)''')
    
    # 2. Create Default Admin (if missing)
    c.execute("SELECT count(*) FROM users WHERE username='admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "admin"))
    
    # --- NEW: Create Default Shopkeeper (if missing) ---
    c.execute("SELECT count(*) FROM users WHERE username='shopkeeper'")
    if c.fetchone()[0] == 0:
        # Default PIN is 1234
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("shopkeeper", "1234"))

    # 3. Seed Brands (Same as before)
    c.execute("SELECT count(*) FROM brands")
    if c.fetchone()[0] == 0:
        for b in INITIAL_BRANDS:
            c.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?)", (b, True))
            bid = c.lastrowid
            for v in VARIANTS:
                c.execute("INSERT INTO prices VALUES (?, ?, ?)", (bid, v, 500.0))
    
    conn.commit()
    return conn

conn = init_db()

# --- HELPER FUNCTIONS ---
def get_brands():
    return pd.read_sql("SELECT * FROM brands ORDER BY name", conn)

def get_inventory(date_str):
    query = """
    SELECT b.name, i.*, p.price 
    FROM inventory i 
    JOIN brands b ON i.brand_id = b.id 
    LEFT JOIN prices p ON (i.brand_id = p.brand_id AND i.variant = p.variant)
    WHERE date = ?
    """
    return pd.read_sql(query, conn, params=(date_str,))

def initialize_day(date_str):
    """Creates draft entries for a new day based on yesterday's closing."""
    existing = pd.read_sql("SELECT count(*) as cnt FROM inventory WHERE date=?", conn, params=(date_str,))
    if existing.iloc[0]['cnt'] > 0:
        return # Already initialized

    prev_date = (datetime.datetime.strptime(date_str, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Get yesterday's closing or default to 0
    brands = get_brands()
    for _, brand in brands.iterrows():
        for v in VARIANTS:
            # Fetch previous closing
            cur = conn.cursor()
            cur.execute("SELECT closing FROM inventory WHERE date=? AND brand_id=? AND variant=?", 
                        (prev_date, brand['id'], v))
            res = cur.fetchone()
            opening = res[0] if res else 0
            
            # Insert new draft row
            conn.execute("""INSERT OR IGNORE INTO inventory 
                            (date, brand_id, variant, opening, receipts, closing, status) 
                            VALUES (?, ?, ?, ?, 0, 0, 0)""", 
                            (date_str, brand['id'], v, opening))
    conn.commit()

# --- AUTHENTICATION ---
def login_screen():
    st.title("🍷 Wine Shop Manager")
    role = st.selectbox("Select Role", ["Shopkeeper", "Admin"])
    
    if role == "Shopkeeper":
        pin = st.text_input("Enter PIN", type="password")
        if st.button("Login"):
            # --- NEW: Check Database for Shopkeeper PIN ---
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username='shopkeeper'")
            result = cur.fetchone()
            
            # result[0] is the PIN stored in DB
            if result and result[0] == pin:
                st.session_state['role'] = 'shopkeeper'
                st.rerun()
            else:
                st.error("Invalid PIN")
    else:
        # --- UPDATED ADMIN LOGIN ---
        username = st.text_input("Username", value="admin") # Default to admin
        pwd = st.text_input("Enter Password", type="password")
        
        if st.button("Login"):
            # Check DB for user and password
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (username,))
            result = cur.fetchone()
            
            if result and result[0] == pwd:
                st.session_state['role'] = 'admin'
                st.session_state['user'] = username # Remember who logged in
                st.rerun()
            else:
                st.error("Invalid Username or Password")
# --- SHOPKEEPER VIEW (WIZARD) ---
def shopkeeper_view():
    st.markdown("### 🏪 Daily Closing Entry")
    st.info("ℹ️ Workflow: Select a date, enter closing stock counts, review the totals, and submit to Admin.")
    
    # 1. DATE SELECTION (Restricted to Today & Future)
    # min_value=datetime.date.today() ensures they cannot edit past history.
    date = st.date_input(
        "Select Date", 
        datetime.date.today(), 
        min_value=datetime.date.today()
    )
    date_str = date.strftime("%Y-%m-%d")
    
    # Initialize the day if it doesn't exist
    if st.button("Load / Refresh Data"):
        initialize_day(date_str)
        st.session_state['current_date'] = date_str
        st.session_state['wiz_idx'] = 0
        st.rerun()

    # Only show controls if date is loaded
    if 'current_date' in st.session_state and st.session_state['current_date'] == date_str:
        df = get_inventory(date_str)
        
        # Check Locked Status
        if not df.empty and df.iloc[0]['status'] == 2:
            st.warning(f"🔒 Data for {date_str} is APPROVED & LOCKED by Admin.")
            st.dataframe(df[['name', 'variant', 'closing', 'sold', 'revenue']])
            return

        # --- TABS FOR ENTRY METHOD ---
        tab_wiz, tab_import, tab_preview = st.tabs(["🧙‍♂️ Manual Wizard", "📂 Import Excel/CSV", "👀 Final Preview (Report)"])

        # ============================================================
        # TAB 1: MANUAL WIZARD (Search, Prev/Next, Validation)
        # ============================================================
        with tab_wiz:
            st.markdown("""
            **Instructions:**
            * Use **Search** to jump to a specific brand.
            * **Validation:** You cannot enter a number higher than the available stock.
            * **Note:** Sizes with 0 stock are hidden automatically.
            """)
            st.divider()
            
            brands = sorted(df['name'].unique()) # Sort alphabetically
            
            # Initialize Index
            if 'wiz_idx' not in st.session_state: st.session_state['wiz_idx'] = 0
            if st.session_state['wiz_idx'] >= len(brands): st.session_state['wiz_idx'] = 0
            
            # --- A. SEARCH BAR ---
            current_brand_name = brands[st.session_state['wiz_idx']]
            selected_brand = st.selectbox(
                "🔍 Search / Jump to Brand:", 
                brands, 
                index=st.session_state['wiz_idx']
            )
            
            # If user used the dropdown to change brand, update index and rerun
            if selected_brand != current_brand_name:
                st.session_state['wiz_idx'] = list(brands).index(selected_brand)
                st.rerun()

            # --- B. RENDER FORM ---
            idx = st.session_state['wiz_idx']
            current_brand = brands[idx]
            brand_rows = df[df['name'] == current_brand]
            
            st.info(f"Brand {idx + 1} of {len(brands)}")
            st.markdown(f"## 🍾 {current_brand}")
            
            # Check total stock for this brand
            total_brand_stock = (brand_rows['opening'] + brand_rows['receipts']).sum()
            
            if total_brand_stock == 0:
                st.warning(f"⚠️ No stock available for {current_brand} (Opening + Receipts = 0).")
                # Navigation buttons for empty brand
                c1, c2 = st.columns([1, 1])
                if c1.button("⬅️ Previous"):
                    if idx > 0:
                        st.session_state['wiz_idx'] -= 1
                        st.rerun()
                if c2.button("Next ➡️"):
                    if idx < len(brands) - 1:
                        st.session_state['wiz_idx'] += 1
                        st.rerun()
            else:
                with st.form(key=f"form_{idx}"):
                    updates = {}
                    has_visible_variants = False
                    
                    # Create input fields ONLY if stock > 0
                    for _, row in brand_rows.iterrows():
                        v = row['variant']
                        max_val = row['opening'] + row['receipts']
                        
                        if max_val > 0:
                            has_visible_variants = True
                            st.markdown(f"**{v}** (Available: {max_val})")
                            
                            # STRICT VALIDATION: max_value prevents invalid entry
                            closing = st.number_input(
                                f"Closing Stock ({v})", 
                                min_value=0, 
                                max_value=max_val, 
                                value=min(row['closing'], max_val),
                                key=f"wiz_{current_brand}_{v}",
                                help=f"Cannot exceed {max_val}"
                            )
                            updates[(row['brand_id'], v)] = closing
                        else:
                            # Keep existing value (0) if hidden
                            updates[(row['brand_id'], v)] = row['closing']

                    if not has_visible_variants:
                        st.caption("No variants have active stock.")

                    st.divider()
                    
                    # --- C. NAVIGATION BUTTONS ---
                    col_prev, col_next = st.columns([1, 1])
                    go_prev = col_prev.form_submit_button("⬅️ Previous")
                    go_next = col_next.form_submit_button("Next ➡️")
                    
                    if go_prev or go_next:
                        # 1. Save Data
                        for (bid, var), cl_val in updates.items():
                            conn.execute(
                                "UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
                                (cl_val, date_str, bid, var)
                            )
                        conn.commit()
                        
                        # 2. Move Index
                        if go_prev:
                            if idx > 0:
                                st.session_state['wiz_idx'] -= 1
                                st.rerun()
                            else:
                                st.toast("Already at the first brand.")
                                
                        if go_next:
                            if idx < len(brands) - 1:
                                st.session_state['wiz_idx'] += 1
                                st.rerun()
                            else:
                                st.success("You have reached the last brand. Check Final Preview.")

        # ============================================================
        # TAB 2: IMPORT EXCEL/CSV (Existing Logic)
        # ============================================================
        with tab_import:
            st.subheader("Import Closing Stock")
            st.markdown("""
            **Format Requirements:**
            * **Row 1:** Header with Sizes (e.g., '750ml', 'Q', '1L').
            * **Column A:** Brand Names.
            """)
            
            uploaded_file = st.file_uploader("Upload Daily Report", type=["xlsx", "xls", "csv"], key="shop_upload")
            
            if uploaded_file:
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    data_dict = {}

                    if file_ext == 'csv':
                        data_dict['Default'] = pd.read_csv(uploaded_file)
                    else:
                        data_dict = pd.read_excel(uploaded_file, sheet_name=None)
                    
                    sheet_options = list(data_dict.keys())
                    # Auto-select sheet based on date
                    default_idx = 0
                    for i, s_name in enumerate(sheet_options):
                        if date.strftime("%d") in s_name or date.strftime("%b") in s_name:
                            default_idx = i
                            
                    selected_sheet = st.selectbox("Select Sheet", sheet_options, index=default_idx)
                    
                    if st.button("Process Import"):
                        df_imp = data_dict[selected_sheet]
                        df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
                        
                        # Map Columns
                        variant_map = {
                            "2l": "2L", "2000ml": "2L",
                            "1l": "1L", "1000ml": "1L", "full": "1L",
                            "q": "Q", "750ml": "Q", "qt": "Q", "quart": "Q",
                            "p": "P", "375ml": "P", "pint": "P", "half": "P",
                            "n": "N", "180ml": "N", "nip": "N", "quarter": "N"
                        }
                        
                        found_maps = {}
                        for col in df_imp.columns:
                            for key, sys_var in variant_map.items():
                                if key in col:
                                    found_maps[col] = sys_var
                                    break
                        
                        if not found_maps:
                            st.error("❌ No size columns found.")
                        else:
                            # Update DB
                            match_count = 0
                            db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                            brand_map = {name.lower().strip(): bid for bid, name in zip(db_brands['id'], db_brands['name'])}
                            
                            brand_col = df_imp.columns[0]
                            for c in df_imp.columns:
                                if 'brand' in c or 'name' in c or 'item' in c:
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
                                        
                                        # Only update if closing <= available (soft validation for import)
                                        # We rely on Final Preview to catch hard errors, 
                                        # but here we update blindly to allow corrections later.
                                        conn.execute("""
                                            UPDATE inventory 
                                            SET closing = ? 
                                            WHERE date = ? AND brand_id = ? AND variant = ?
                                        """, (closing_qty, date_str, bid, sys_var))
                                    match_count += 1
                                    
                            conn.commit()
                            st.success(f"✅ Imported {match_count} brands!")
                            
                except Exception as e:
                    st.error(f"Import Error: {e}")

        # ============================================================
        # TAB 3: FINAL PREVIEW (FIXED)
        # ============================================================
        with tab_preview:
            st.subheader("📊 Final Daily Report")
            
            # 1. Prepare Data
            df['available'] = df['opening'] + df['receipts']
            df['sold'] = df['available'] - df['closing']
            df['item_revenue'] = df['sold'] * df['price']
            
            # 2. Validation
            negatives = df[df['sold'] < 0]
            if not negatives.empty:
                st.error("❌ ERROR: You have entered Closing Stock > Available Stock.")
                st.dataframe(negatives[['name', 'variant', 'available', 'closing', 'sold']])
                st.stop()

            # 3. Create Pivot Tables
            variants_order = ["2L", "1L", "Q", "P", "N"]
            
            def make_pivot(val_col):
                p = df.pivot_table(index='name', columns='variant', values=val_col, aggfunc='sum').fillna(0)
                for v in variants_order:
                    if v not in p.columns: p[v] = 0
                return p[variants_order]

            p_open = make_pivot('available')
            p_close = make_pivot('closing')
            p_sold = make_pivot('sold')
            
            revenue_series = df.groupby('name')['item_revenue'].sum()

            # 4. Create MultiIndex Headers
            p_open.columns = pd.MultiIndex.from_product([['Opening (Inc Rcpt)'], p_open.columns])
            p_close.columns = pd.MultiIndex.from_product([['Closing Stock'], p_close.columns])
            p_sold.columns = pd.MultiIndex.from_product([['Sales'], p_sold.columns])

            # 5. Combine
            final_df = pd.concat([p_open, p_close, p_sold], axis=1)
            final_df[('Sales', 'Revenue (₹)')] = revenue_series
            final_df = final_df.fillna(0)

            # --- THE FIX: FLATTEN COLUMNS FOR DISPLAY ---
            # Streamlit cannot handle Tuple keys in column_config (e.g. ('Sales', 'Revenue')).
            # We convert columns to simple strings just for the display dataframe.
            
            # 1. Create a display copy
            display_df = final_df.copy()
            
            # 2. Flatten headers: "Sales" + "Revenue" -> "Sales_Revenue"
            # This makes the dataframe safe for Streamlit to render
            display_df.columns = ['_'.join(col).strip() for col in display_df.columns.values]

            # 3. Rename the specific revenue column to something clean for config
            # It will now look like "Sales_Revenue (₹)"
            
            # 6. Display
            st.dataframe(
                final_df, # We pass the original MultiIndex DF, Streamlit handles the visual
                use_container_width=True, 
                height=600,
                # REMOVED column_config mapping for the Tuple key to prevent the crash.
                # If you need specific formatting, we apply it to the flattened version or rely on defaults.
            )
            
            # 7. Total Summary Metrics
            total_rev = df['item_revenue'].sum()
            st.metric("💰 Total Shop Revenue", f"₹ {total_rev:,.2f}")
            
            # 8. Submit
            if st.button("✅ Submit Final Report to Admin", type="primary"):
                conn.execute("UPDATE inventory SET status=1 WHERE date=?", (date_str,))
                conn.commit()
                st.balloons()
                st.success("Report Submitted Successfully!")

# --- ADMIN VIEW ---
def admin_view():
    st.sidebar.title("Admin Menu")
    menu = st.sidebar.radio("Go to", ["Dashboard", "🚚 Stock Intake", "Brand Manager", "Import Excel", "Settings"])
    
    # --- 1. DASHBOARD ---
    if menu == "Dashboard":
        st.header("📋 Approval Dashboard")
        st.markdown("""
        **Overview:**
        * View daily sales summaries.
        * Approve or Reject closing stock submissions from shopkeepers.
        * Export inventory reports to CSV for accounting.
        """)
        
        # Export Data Button
        st.subheader("Export Data")
        st.info("ℹ️ Select a date to download a complete report of Opening, Receipts, Closing, and Revenue.")
        
        export_date = st.date_input("Select Date for Report", datetime.date.today())
        date_str = export_date.strftime("%Y-%m-%d")
        
        df_export = get_inventory(date_str)
        if not df_export.empty:
            df_export['sold'] = (df_export['opening'] + df_export['receipts']) - df_export['closing']
            df_export['revenue'] = df_export['sold'] * df_export['price']
            csv_data = df_export[['name', 'variant', 'opening', 'receipts', 'closing', 'sold', 'revenue', 'status']].to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download CSV Report", data=csv_data, file_name=f"inventory_{date_str}.csv", mime="text/csv")
        else:
            st.warning(f"No data found for {date_str}")
            
        st.divider()
        
        # Pending Approvals
        st.subheader("Pending Approvals")
        pending = pd.read_sql("SELECT DISTINCT date FROM inventory WHERE status=1", conn)
        if pending.empty:
            st.success("All caught up! No pending approvals.")
        else:
            for d in pending['date']:
                with st.expander(f"🔔 Pending Submission: {d}"):
                    data = get_inventory(d)
                    data['sold'] = (data['opening'] + data['receipts']) - data['closing']
                    data['revenue'] = data['sold'] * data['price']
                    st.dataframe(data)
                    st.write(f"**Total Revenue:** ₹{data['revenue'].sum():,.2f}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Approve & Lock", key=f"app_{d}"):
                        conn.execute("UPDATE inventory SET status=2 WHERE date=?", (d,))
                        conn.commit()
                        st.success(f"Approved {d}")
                        st.rerun()
                    if c2.button("🔓 Unlock/Reject", key=f"rej_{d}"):
                        conn.execute("UPDATE inventory SET status=0 WHERE date=?", (d,))
                        conn.commit()
                        st.warning(f"Returned {d} to Shopkeeper")
                        st.rerun()

    # --- 2. STOCK INTAKE (RECEIPTS) ---
    elif menu == "🚚 Stock Intake":
        st.header("🚚 Add New Stock (Receipts)")
        
        # Select Date & Initialize
        date_in = st.date_input("Date of Receipt", datetime.date.today())
        date_str = date_in.strftime("%Y-%m-%d")
        
        if st.button("Load Inventory for Date"):
            initialize_day(date_str)
            st.session_state['stock_date'] = date_str
            st.rerun()

        if 'stock_date' in st.session_state and st.session_state['stock_date'] == date_str:
            
            # --- TABS ---
            tab_manual, tab_excel, tab_pdf = st.tabs(["✋ Manual Entry", "📂 Import Excel", "📄 Import PDF"])
            
            # === TAB 1: MANUAL ENTRY ===
            with tab_manual:
                st.info(f"Manually enter quantities for a single brand for {date_str}.")
                brands_df = get_brands()
                brand_sel = st.selectbox("Select Brand Received", brands_df['name'])
                
                if brand_sel:
                    bid = brands_df[brands_df['name'] == brand_sel].iloc[0]['id']
                    cur_rows = pd.read_sql("SELECT variant, receipts FROM inventory WHERE date=? AND brand_id=?", 
                                           conn, params=(date_str, bid))
                    
                    with st.form("receipt_form"):
                        st.subheader(f"Enter Quantities for {brand_sel}")
                        cols = st.columns(len(VARIANTS))
                        input_vals = {}
                        
                        for i, v_name in enumerate(VARIANTS):
                            row = cur_rows[cur_rows['variant'] == v_name]
                            current_qty = 0 if row.empty else row.iloc[0]['receipts']
                            with cols[i]:
                                new_qty = st.number_input(f"{v_name}", min_value=0, value=current_qty, key=f"rec_{bid}_{v_name}")
                                input_vals[v_name] = new_qty
                        
                        if st.form_submit_button("➕ Update Receipts"):
                            for v, qty in input_vals.items():
                                conn.execute("UPDATE inventory SET receipts=? WHERE date=? AND brand_id=? AND variant=?",
                                             (qty, date_str, bid, v))
                            conn.commit()
                            st.success(f"Updated stock receipts for {brand_sel}!")
                            st.rerun()

            # === TAB 2: IMPORT EXCEL/CSV ===
            with tab_excel:
                st.subheader("📂 Bulk Import Receipts")
                st.markdown("""
                ### 📋 File Format Requirements
                * **File Types:** `.xlsx`, `.xls`, `.csv`
                * **Sheets:** Supports multiple sheets. You will select one sheet to import.
                * **Columns:** Must contain headers indicating sizes (e.g., `750ml`, `Q`, `1L`, `Full`, `Half`).
                * **Rows:** Must contain a column for Brand Name.
                
                **Example Layout:**
                | Brand Name | 750ml | 375ml | 180ml |
                | :--- | :--- | :--- | :--- |
                | Royal Stag | 12 | 24 | 48 |
                """)
                
                uploaded_file = st.file_uploader("Upload Receipt File", type=["xlsx", "xls", "csv"], key="receipt_upload")
                
                if uploaded_file:
                    try:
                        # 1. Parse File & Sheets
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        data_dict = {}
                        
                        if file_ext == 'csv':
                            data_dict['Default'] = pd.read_csv(uploaded_file)
                        else:
                            data_dict = pd.read_excel(uploaded_file, sheet_name=None)
                        
                        sheet_options = list(data_dict.keys())
                        
                        # Auto-guess sheet based on selected date
                        default_idx = 0
                        for i, s_name in enumerate(sheet_options):
                            if date_in.strftime("%d") in s_name or date_in.strftime("%b") in s_name:
                                default_idx = i
                                
                        selected_sheet = st.selectbox("Select Sheet to Import", sheet_options, index=default_idx)
                        
                        if st.button("🚀 Process Import"):
                            df_imp = data_dict[selected_sheet]
                            # Clean headers
                            df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
                            
                            # 2. Map Columns (Reusable Logic)
                            variant_map = {
                                "2l": "2L", "2000ml": "2L",
                                "1l": "1L", "1000ml": "1L", "full": "1L",
                                "q": "Q", "750ml": "Q", "qt": "Q", "quart": "Q",
                                "p": "P", "375ml": "P", "pint": "P", "half": "P",
                                "n": "N", "180ml": "N", "nip": "N", "quarter": "N"
                            }
                            
                            found_maps = {}
                            for col in df_imp.columns:
                                for key, sys_var in variant_map.items():
                                    if key in col:
                                        found_maps[col] = sys_var
                                        break
                            
                            if not found_maps:
                                st.error("❌ No size columns found. Check headers (need '750ml', 'Q', etc).")
                            else:
                                # 3. Map Brands & Update DB
                                db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                                brand_map = {name.lower().strip(): bid for bid, name in zip(db_brands['id'], db_brands['name'])}
                                
                                # Identify Brand Column
                                brand_col = df_imp.columns[0]
                                for c in df_imp.columns:
                                    if 'brand' in c or 'name' in c or 'item' in c:
                                        brand_col = c
                                        break
                                
                                match_count = 0
                                for _, row in df_imp.iterrows():
                                    file_brand = str(row[brand_col]).strip()
                                    bid = brand_map.get(file_brand.lower())
                                    
                                    if bid:
                                        for col_name, sys_var in found_maps.items():
                                            # Get Receipt Value
                                            try:
                                                val = row[col_name]
                                                receipt_qty = int(float(val))
                                            except:
                                                receipt_qty = 0
                                            
                                            if receipt_qty > 0:
                                                conn.execute("""
                                                    UPDATE inventory 
                                                    SET receipts = ? 
                                                    WHERE date = ? AND brand_id = ? AND variant = ?
                                                """, (receipt_qty, date_str, bid, sys_var))
                                        match_count += 1
                                
                                conn.commit()
                                st.success(f"✅ Imported receipts for {match_count} brands successfully!")
                                st.balloons()
                                
                    except Exception as e:
                        st.error(f"Import Error: {e}")
            with tab_pdf:
                st.subheader("📄 Import from Official Receipt PDF")
                st.markdown("""
                **Instructions:**
                1. Upload the 'Invoice Cum Delivery Challan' PDF.
                2. System extracts the inventory table automatically.
                3. **Cases are converted to bottles** (e.g., 1 Case 180ml = 48 bottles).
                4. Brand names like 'Vat 69 Blended...' are matched to 'Vat 69'.
                """)
                
                uploaded_pdf = st.file_uploader("Upload Receipt PDF", type=["pdf"], key="pdf_upload")
                
                if uploaded_pdf:
                    if st.button("🔍 Process PDF"):
                        try:
                            # 1. Get DB Brands for matching
                            db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                            # List of tuples: [('Royal Stag', 1), ('Vat 69', 2)...]
                            # Sort by length desc to match longest names first
                            db_brands_list = sorted(
                                list(zip(db_brands['name'], db_brands['id'])), 
                                key=lambda x: len(x[0]), 
                                reverse=True
                            )
                            
                            # 2. Extract Data
                            df_extracted = parse_pdf_receipt(uploaded_pdf, db_brands_list)
                            
                            if df_extracted.empty:
                                st.error("❌ No valid inventory data found. Check PDF format.")
                            else:
                                st.success(f"✅ Extracted {len(df_extracted)} items!")
                                
                                # 3. Show Preview
                                st.subheader("Preview Data to Import")
                                st.dataframe(df_extracted[['brand_name', 'variant', 'qty', 'raw_pdf_brand']])
                                
                                # 4. Commit Button
                                if st.button("🚀 Add to Inventory"):
                                    count = 0
                                    for _, row in df_extracted.iterrows():
                                        conn.execute("""
                                            UPDATE inventory 
                                            SET receipts = receipts + ? 
                                            WHERE date = ? AND brand_id = ? AND variant = ?
                                        """, (row['qty'], date_str, row['brand_id'], row['variant']))
                                        count += 1
                                    conn.commit()
                                    st.success(f"🎉 Successfully added {count} items to stock receipts!")
                                    st.balloons()
                                    
                        except Exception as e:
                            st.error(f"PDF Processing Error: {e}")
            # --- SHOW SUMMARY BELOW TABS ---
            st.divider()
            st.markdown("### 📊 Today's Total Receipts")
            daily_rec = pd.read_sql("""
                SELECT b.name, i.variant, i.receipts 
                FROM inventory i JOIN brands b ON i.brand_id = b.id
                WHERE i.date=? AND i.receipts > 0
                ORDER BY b.name
            """, conn, params=(date_str,))
            
            if not daily_rec.empty:
                st.dataframe(daily_rec, use_container_width=True)
            else:
                st.caption("No stock receipts recorded yet for this date.")

    # --- 3. BRAND MANAGER ---
    elif menu == "Brand Manager":
        st.header("🏷️ Manage Brands & Prices")
        st.markdown("""
        **Purpose:** Add new brand names or update the selling price for existing brands.
        * **Add Brand:** Creates a new brand entry with 0 price.
        * **Edit Prices:** Sets the selling price (used for Revenue calculation).
        """)
        
        # --- 1. Add New Brand ---
        with st.expander("➕ Add New Brand Manually"):
            new_brand = st.text_input("New Brand Name")
            if st.button("Add Brand"):
                if new_brand:
                    try:
                        conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?)", (new_brand, True))
                        bid = conn.cursor().execute("SELECT last_insert_rowid()").fetchone()[0]
                        # Create default prices
                        for v in VARIANTS:
                            conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, ?)", (bid, v, 0.0))
                        conn.commit()
                        st.success(f"Added {new_brand}!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Brand already exists.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.divider()

        # --- 2. Edit Prices (SELF-HEALING VERSION) ---
        st.subheader("Edit Prices")
        brands_df = get_brands()
        
        if not brands_df.empty:
            b_sel = st.selectbox("Select Brand to Edit", brands_df['name'])
            
            if b_sel:
                bid = brands_df[brands_df['name'] == b_sel].iloc[0]['id']
                prices = pd.read_sql("SELECT * FROM prices WHERE brand_id=?", conn, params=(bid,))
                
                # Auto-fix missing prices
                if len(prices) < len(VARIANTS):
                    st.toast(f"⚠️ Repairing data for {b_sel}...")
                    for v in VARIANTS:
                        conn.execute("INSERT OR IGNORE INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))
                    conn.commit()
                    prices = pd.read_sql("SELECT * FROM prices WHERE brand_id=?", conn, params=(bid,))
                
                with st.form("price_edit_form"):
                    st.write(f"Editing prices for: **{b_sel}**")
                    input_values = {}
                    cols = st.columns(len(VARIANTS))
                    
                    for i, v_name in enumerate(VARIANTS):
                        row = prices[prices['variant'] == v_name]
                        current_val = 0.0
                        if not row.empty:
                            current_val = row.iloc[0]['price']
                        
                        with cols[i]:
                            new_val = st.number_input(f"{v_name}", value=float(current_val), min_value=0.0, step=10.0, key=f"price_{bid}_{v_name}")
                            input_values[v_name] = new_val
                    
                    st.caption("Enter price in Rupees (₹)")
                    if st.form_submit_button("💾 Save Updated Prices"):
                        for var, price in input_values.items():
                            conn.execute("UPDATE prices SET price=? WHERE brand_id=? AND variant=?", (price, bid, var))
                        conn.commit()
                        st.success(f"Prices for {b_sel} updated!")
                        st.rerun()
        else:
            st.info("No brands found in database.")

    # --- 4. IMPORT EXCEL ---
    elif menu == "Import Excel":
        st.header("📥 Import Brands Master List")
        st.markdown("""
        **Purpose:** Bulk create brand names from an Excel list.
        
        ### 📋 File Format Requirements
        * **File Types:** `.xlsx`, `.xls`, `.csv`
        * **Sheets:** Supports multiple sheets. All sheets will be scanned.
        * **Column A:** Must contain **Brand Names**.
        * **Row 1 & 2:** Ignored (Reserved for headers).
        * **Row 3:** Data starts here.
        
        **Example Layout:**
        | | A | B |
        | :--- | :--- | :--- |
        | **1** | *Header* | ... |
        | **2** | *Header* | ... |
        | **3** | **Royal Stag** | ... |
        | **4** | **Old Monk** | ... |
        """)
        
        uploaded_file = st.file_uploader("Choose file", type=["xlsx", "xls", "csv"])
        
        if uploaded_file:
            if st.button("Process Import"):
                all_brands = set()
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    if file_ext == 'csv':
                        df = pd.read_csv(uploaded_file, header=None, skiprows=2)
                        brands_found = df[0].dropna().astype(str).tolist()
                        all_brands.update(brands_found)
                    elif file_ext in ['xlsx', 'xls']:
                        xls_data = pd.read_excel(uploaded_file, sheet_name=None, header=None, skiprows=2)
                        for sheet_name, df in xls_data.items():
                            if not df.empty:
                                brands_found = df[0].dropna().astype(str).tolist()
                                all_brands.update(brands_found)
                                st.write(f"Found {len(brands_found)} brands in sheet: *{sheet_name}*")

                    count = 0
                    for b in all_brands:
                        clean_name = b.strip()
                        if len(clean_name) > 0:
                            try:
                                conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?)", (clean_name, True))
                                bid = conn.cursor().execute("SELECT last_insert_rowid()").fetchone()[0]
                                for v in VARIANTS:
                                    conn.execute("INSERT INTO prices VALUES (?, ?, ?)", (bid, v, 0.0))
                                count += 1
                            except sqlite3.IntegrityError:
                                pass

                    conn.commit()
                    if count > 0:
                        st.success(f"✅ Successfully imported {count} new brands!")
                    else:
                        st.warning("No new brands found (duplicates skipped).")
                        
                except Exception as e:
                    st.error(f"❌ Import failed: {e}")

    # --- 5. SETTINGS ---
    elif menu == "Settings":
        st.header("⚙️ Admin Settings")
        st.markdown("**Purpose:** Manage access credentials for yourself and shopkeepers.")
        
        with st.expander("👤 Change Admin Password", expanded=False):
            with st.form("change_pass_form"):
                current_user = st.session_state.get('user', 'admin')
                new_pass = st.text_input("New Admin Password", type="password")
                if st.form_submit_button("Update My Password"):
                    conn.execute("UPDATE users SET password=? WHERE username=?", (new_pass, current_user))
                    conn.commit()
                    st.success("Admin password updated.")

        st.divider()
        st.subheader("🏪 Shopkeeper Access")
        with st.form("change_pin_form"):
            st.write("Update the PIN used by shopkeepers on the main login screen.")
            new_pin = st.text_input("New Shopkeeper PIN", max_chars=6)
            
            if st.form_submit_button("Update PIN"):
                if len(new_pin) > 0:
                    try:
                        conn.execute("UPDATE users SET password=? WHERE username='shopkeeper'", (new_pin,))
                        conn.commit()
                        st.success(f"Shopkeeper PIN changed to: {new_pin}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.error("PIN cannot be empty.")
        st.divider()
        st.subheader("💾 System Backup")
        st.markdown("Download a copy of the entire database to keep your data safe.")
        
        # Read the DB file as binary
        try:
            with open("wineshop.db", "rb") as f:
                db_bytes = f.read()
                
            st.download_button(
                label="📥 Download Database Backup (.db)",
                data=db_bytes,
                file_name=f"wineshop_backup_{datetime.date.today()}.db",
                mime="application/octet-stream"
            )
        except Exception as e:
            st.error(f"Could not read database file: {e}")
# --- MAIN APP ROUTING ---
if 'role' not in st.session_state:
    login_screen()
else:
    if st.sidebar.button("Logout"):
        del st.session_state['role']
        st.rerun()
        
    if st.session_state['role'] == 'shopkeeper':
        shopkeeper_view()
    elif st.session_state['role'] == 'admin':
        admin_view()
