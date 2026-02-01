# --- STANDARD IMPORTS ---
import streamlit as st
import pandas as pd
import sqlite3
import datetime
import os

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
    
    # 1. Date Selection
    date = st.date_input("Select Date", datetime.date.today())
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
            st.warning(f"🔒 Data for {date_str} is LOCKED/APPROVED.")
            st.dataframe(df[['name', 'variant', 'closing', 'sold', 'revenue']])
            return

        # --- TABS FOR ENTRY METHOD ---
        tab_wiz, tab_import, tab_preview = st.tabs(["🧙‍♂️ Manual Wizard", "📂 Import Excel/CSV", "👀 Final Preview"])

        # --- TAB 1: EXISTING MANUAL WIZARD ---
        with tab_wiz:
            brands = df['name'].unique()
            if 'wiz_idx' not in st.session_state: st.session_state['wiz_idx'] = 0
            idx = st.session_state['wiz_idx']
            
            if idx < len(brands):
                current_brand = brands[idx]
                brand_rows = df[df['name'] == current_brand]
                
                st.info(f"Brand {idx + 1}/{len(brands)}")
                st.markdown(f"## 🍾 {current_brand}")
                
                with st.form(key=f"form_{idx}"):
                    updates = {}
                    for _, row in brand_rows.iterrows():
                        v = row['variant']
                        st.markdown(f"**{v}** (Open: {row['opening']} + Rcv: {row['receipts']})")
                        max_val = row['opening'] + row['receipts']
                        closing = st.number_input(f"Closing Stock", min_value=0, value=row['closing'], key=f"wiz_{current_brand}_{v}")
                        updates[(row['brand_id'], v)] = closing
                    
                    if st.form_submit_button("Next Brand ➡️"):
                        for (bid, var), cl_val in updates.items():
                            conn.execute("UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
                                         (cl_val, date_str, bid, var))
                        conn.commit()
                        st.session_state['wiz_idx'] += 1
                        st.rerun()
            else:
                st.success("Manual Entry Complete. Check Preview Tab.")
                if st.button("Restart Wizard"):
                    st.session_state['wiz_idx'] = 0
                    st.rerun()

        # --- TAB 2: NEW IMPORT FEATURE ---
        with tab_import:
            st.subheader("Import Closing Stock")
            st.markdown("""
            **Format Guide:**
            * **Row 1:** Header with Brand Name and Sizes (e.g., 'Brand', '2L', '750ml', 'Q').
            * **Rows:** Brand names.
            * **Cells:** Closing quantity.
            """)
            
            uploaded_file = st.file_uploader("Upload Daily Report", type=["xlsx", "xls", "csv"])
            
            if uploaded_file:
                # 1. READ FILE
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    data_dict = {} # {SheetName: DataFrame}

                    if file_ext == 'csv':
                        data_dict['Default'] = pd.read_csv(uploaded_file)
                    else:
                        # Read all sheets
                        data_dict = pd.read_excel(uploaded_file, sheet_name=None)
                    
                    # 2. SELECT SHEET
                    sheet_options = list(data_dict.keys())
                    st.write(f"📄 Found {len(sheet_options)} sheet(s).")
                    
                    # Try to auto-select sheet matching the date (e.g., "01-02", "Feb 1")
                    default_idx = 0
                    for i, s_name in enumerate(sheet_options):
                        if date.strftime("%d") in s_name or date.strftime("%b") in s_name:
                            default_idx = i
                            
                    selected_sheet = st.selectbox("Select Sheet for Today's Data", sheet_options, index=default_idx)
                    
                    if st.button("Process Closing Stock Import"):
                        df_imp = data_dict[selected_sheet]
                        
                        # Clean column headers (strip spaces, lower case)
                        df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
                        
                        # 3. MAP COLUMNS TO VARIANTS
                        # Map common Excel headers to our System Variants: 2L, 1L, Q, P, N
                        variant_map = {
                            "2l": "2L", "2000ml": "2L",
                            "1l": "1L", "1000ml": "1L", "full": "1L",
                            "q": "Q", "750ml": "Q", "qt": "Q", "quart": "Q",
                            "p": "P", "375ml": "P", "pint": "P", "half": "P",
                            "n": "N", "180ml": "N", "nip": "N", "quarter": "N"
                        }
                        
                        # Find which columns exist in this Excel file
                        found_maps = {} # {ExcelColName: SystemVariant}
                        for col in df_imp.columns:
                            for key, sys_var in variant_map.items():
                                if key in col: # partial match (e.g., "750ml bottles" matches "750ml")
                                    found_maps[col] = sys_var
                                    break
                        
                        if not found_maps:
                            st.error("❌ Could not identify any size columns (2L, 750ml, etc.). Check your headers.")
                        else:
                            st.write(f"✅ Mapped Columns: {found_maps}")
                            
                            # 4. UPDATE DATABASE
                            match_count = 0
                            # Get existing brands mapping to IDs
                            db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                            # Create dictionary for fast lookup {lower_name: id}
                            brand_map = {name.lower().strip(): bid for bid, name in zip(db_brands['id'], db_brands['name'])}
                            
                            # Identify Brand Name column (usually col 0 or 'brand' or 'name')
                            brand_col = df_imp.columns[0] # Default to first column
                            for c in df_imp.columns:
                                if 'brand' in c or 'name' in c or 'item' in c:
                                    brand_col = c
                                    break
                            
                            for _, row in df_imp.iterrows():
                                file_brand = str(row[brand_col]).strip()
                                bid = brand_map.get(file_brand.lower())
                                
                                if bid:
                                    for col_name, sys_var in found_maps.items():
                                        # Get closing value from file
                                        val = row[col_name]
                                        # Clean value (handle NaN or strings)
                                        try:
                                            closing_qty = int(float(val))
                                        except:
                                            closing_qty = 0
                                        
                                        # Update DB
                                        conn.execute("""
                                            UPDATE inventory 
                                            SET closing = ? 
                                            WHERE date = ? AND brand_id = ? AND variant = ?
                                        """, (closing_qty, date_str, bid, sys_var))
                                    match_count += 1
                                    
                            conn.commit()
                            st.success(f"✅ Successfully updated closing stock for {match_count} brands!")
                            st.balloons()
                            
                except Exception as e:
                    st.error(f"Error parsing file: {e}")

        # --- TAB 3: PREVIEW & SUBMIT (Existing Logic) ---
        with tab_preview:
            st.subheader("Review & Submit")
            
            # Recalculate totals
            df_final = get_inventory(date_str)
            df_final['sold'] = (df_final['opening'] + df_final['receipts']) - df_final['closing']
            df_final['revenue'] = df_final['sold'] * df_final['price']
            
            total_rev = df_final['revenue'].sum()
            st.metric("Total Revenue Estimate", f"₹{total_rev:,.2f}")
            
            # Show negative stock warning
            negatives = df_final[df_final['sold'] < 0]
            if not negatives.empty:
                st.error("⚠️ Warning: Some items have Closing Stock > Opening + Receipts!")
                st.dataframe(negatives[['name', 'variant', 'opening', 'receipts', 'closing', 'sold']])
            
            st.dataframe(df_final[['name', 'variant', 'closing', 'sold', 'revenue']], use_container_width=True)
            
            if st.button("Submit to Admin 📤"):
                if not negatives.empty:
                    st.error("Cannot submit while there are negative sales errors. Please fix closing counts.")
                else:
                    conn.execute("UPDATE inventory SET status=1 WHERE date=?", (date_str,))
                    conn.commit()
                    st.success("Submitted to Admin successfully!")

# --- ADMIN VIEW ---
def admin_view():
    st.sidebar.title("Admin Menu")
    menu = st.sidebar.radio("Go to", ["Dashboard", "🚚 Stock Intake", "Brand Manager", "Import Excel", "Settings"])
    
    # --- 1. DASHBOARD ---
    if menu == "Dashboard":
        st.header("📋 Approval Dashboard")
        
        # Export Data Button
        st.subheader("Export Data")
        export_date = st.date_input("Select Date for Report", datetime.date.today())
        date_str = export_date.strftime("%Y-%m-%d")
        
        df_export = get_inventory(date_str)
        if not df_export.empty:
            df_export['sold'] = (df_export['opening'] + df_export['receipts']) - df_export['closing']
            df_export['revenue'] = df_export['sold'] * df_export['price']
            csv_data = df_export[['name', 'variant', 'opening', 'receipts', 'closing', 'sold', 'revenue', 'status']].to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download CSV Report", data=csv_data, file_name=f"inventory_{date_str}.csv", mime="text/csv")
        else:
            st.info(f"No data found for {date_str}")
            
        st.divider()
        
        # Pending Approvals
        pending = pd.read_sql("SELECT DISTINCT date FROM inventory WHERE status=1", conn)
        if pending.empty:
            st.info("No pending approvals.")
        else:
            for d in pending['date']:
                with st.expander(f"Pending: {d}"):
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

    # --- 2. NEW: STOCK INTAKE (RECEIPTS) ---
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
            
            # --- TABS FOR ENTRY METHOD ---
            tab_manual, tab_import = st.tabs(["✋ Manual Entry", "📂 Import Excel/CSV"])
            
            # === TAB 1: MANUAL ENTRY ===
            with tab_manual:
                st.info(f"Adding stock manually for: {date_str}")
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
            with tab_import:
                st.subheader("📂 Bulk Import Receipts")
                st.markdown("""
                **Instructions:**
                1. Upload a file (.xlsx, .xls, .csv).
                2. Select the **Sheet** corresponding to today's date.
                3. Ensure headers contain sizes (e.g., '750ml', 'Q', '1L').
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
                        st.write(f"📄 Found {len(sheet_options)} sheet(s).")
                        
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
        st.header("🏷️ Manage Brands")
        
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
                # Get Brand ID
                bid = brands_df[brands_df['name'] == b_sel].iloc[0]['id']
                
                # Fetch current prices
                prices = pd.read_sql("SELECT * FROM prices WHERE brand_id=?", conn, params=(bid,))
                
                # --- AUTO-FIX: If prices are missing, create them now ---
                if len(prices) < len(VARIANTS):
                    st.toast(f"⚠️ Repairing data for {b_sel}...")
                    for v in VARIANTS:
                        # Insert only if missing
                        conn.execute("""
                            INSERT OR IGNORE INTO prices (brand_id, variant, price) 
                            VALUES (?, ?, 0.0)
                        """, (bid, v))
                    conn.commit()
                    # Re-fetch after repair
                    prices = pd.read_sql("SELECT * FROM prices WHERE brand_id=?", conn, params=(bid,))
                
                # --- DISPLAY FORM ---
                with st.form("price_edit_form"):
                    st.write(f"Editing prices for: **{b_sel}**")
                    input_values = {}
                    
                    # Create 5 columns for the 5 variants
                    cols = st.columns(len(VARIANTS))
                    
                    # We loop through the STANDARD variants list to ensure order (2L, 1L, Q, P, N)
                    for i, v_name in enumerate(VARIANTS):
                        # Find the row for this variant
                        row = prices[prices['variant'] == v_name]
                        
                        # Default to 0.0 if something is still weird, otherwise use DB value
                        current_val = 0.0
                        if not row.empty:
                            current_val = row.iloc[0]['price']
                        
                        with cols[i]:
                            new_val = st.number_input(
                                f"{v_name}", 
                                value=float(current_val),
                                min_value=0.0,
                                step=10.0,
                                key=f"price_{bid}_{v_name}"
                            )
                            input_values[v_name] = new_val
                    
                    st.caption("Enter price in Rupees (₹)")
                    
                    if st.form_submit_button("💾 Save Updated Prices"):
                        for var, price in input_values.items():
                            conn.execute(
                                "UPDATE prices SET price=? WHERE brand_id=? AND variant=?", 
                                (price, bid, var)
                            )
                        conn.commit()
                        st.success(f"Prices for {b_sel} updated!")
                        st.rerun()
        else:
            st.info("No brands found in database.")

    elif menu == "Import Excel":
        st.header("📥 Import Brands")
        st.markdown("""
        **Instructions:**
        * Supports **.xlsx**, **.xls**, and **.csv**.
        * Reads **Column A** (starting Row 3) for Brand Names.
        * If file has multiple sheets, **all sheets** will be processed.
        """)
        
        # 1. Accept multiple file types
        uploaded_file = st.file_uploader("Choose file", type=["xlsx", "xls", "csv"])
        
        if uploaded_file:
            if st.button("Process Import"):
                all_brands = set() # Use a set to automatically avoid duplicates in memory
                
                try:
                    # 2. Determine File Type & Read Data
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    
                    if file_ext == 'csv':
                        # Read CSV (Single Sheet)
                        df = pd.read_csv(uploaded_file, header=None, skiprows=2)
                        brands_found = df[0].dropna().astype(str).tolist()
                        all_brands.update(brands_found)
                        
                    elif file_ext in ['xlsx', 'xls']:
                        # Read Excel (Multiple Sheets)
                        # sheet_name=None reads ALL sheets into a dictionary
                        xls_data = pd.read_excel(uploaded_file, sheet_name=None, header=None, skiprows=2)
                        
                        for sheet_name, df in xls_data.items():
                            if not df.empty:
                                # Assume Column A is index 0
                                brands_found = df[0].dropna().astype(str).tolist()
                                all_brands.update(brands_found)
                                st.write(f"Found {len(brands_found)} brands in sheet: *{sheet_name}*")

                    # 3. Save to Database
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
                                pass # Brand already exists, skip it

                    conn.commit()
                    
                    if count > 0:
                        st.success(f"✅ Successfully imported {count} new brands!")
                    else:
                        st.warning("No new brands found (duplicates skipped).")
                        
                except Exception as e:
                    st.error(f"❌ Import failed: {e}")
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
