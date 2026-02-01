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
    
    # 1. Date Picker
    date = st.date_input("Select Date", datetime.date.today())
    date_str = date.strftime("%Y-%m-%d")
    
    if st.button("Load Data"):
        initialize_day(date_str)
        st.session_state['current_date'] = date_str
        st.session_state['wiz_idx'] = 0 # Reset wizard index
        st.rerun()

    if 'current_date' in st.session_state and st.session_state['current_date'] == date_str:
        df = get_inventory(date_str)
        
        # Check Status
        if not df.empty and df.iloc[0]['status'] == 2:
            st.warning(f"🔒 Data for {date_str} is LOCKED/APPROVED.")
            st.dataframe(df[['name', 'variant', 'opening', 'receipts', 'closing']])
            return

        brands = df['name'].unique()
        
        # Wizard Logic
        if 'wiz_idx' not in st.session_state:
            st.session_state['wiz_idx'] = 0
            
        idx = st.session_state['wiz_idx']
        
        if idx < len(brands):
            current_brand = brands[idx]
            brand_rows = df[df['name'] == current_brand]
            
            st.info(f"Brand {idx + 1}/{len(brands)}")
            st.markdown(f"## 🍾 {current_brand}")
            
            with st.form(key=f"form_{idx}"):
                # Iterate variants for this brand
                updates = {}
                for _, row in brand_rows.iterrows():
                    v = row['variant']
                    st.markdown(f"**Variant: {v}**")
                    c1, c2, c3 = st.columns(3)
                    c1.text(f"Open: {row['opening']}")
                    c2.text(f"Recvd: {row['receipts']}")
                    
                    max_val = row['opening'] + row['receipts']
                    
                    # Shopkeeper Input
                    closing = c3.number_input(f"Closing ({v})", min_value=0, value=row['closing'], key=f"{current_brand}_{v}")
                    
                    # Validation Display
                    sold = max_val - closing
                    rev = sold * row['price']
                    if closing > max_val:
                        st.error(f"❌ Error: Closing cannot exceed {max_val}")
                    else:
                        st.caption(f"✅ Sold: {sold} | Revenue: ₹{rev:,.2f}")
                    
                    updates[(row['brand_id'], v)] = closing

                # Navigation
                col_back, col_next = st.columns([1, 1])
                with col_next:
                    if st.form_submit_button("Next Brand ➡️"):
                        # Save current inputs to DB
                        for (bid, var), cl_val in updates.items():
                            conn.execute("UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
                                         (cl_val, date_str, bid, var))
                        conn.commit()
                        st.session_state['wiz_idx'] += 1
                        st.rerun()
        else:
            # Summary Screen
            st.success("🎉 Entry Complete!")
            st.subheader("Preview Summary")
            
            # Recalculate totals
            df_final = get_inventory(date_str)
            df_final['sold'] = (df_final['opening'] + df_final['receipts']) - df_final['closing']
            df_final['revenue'] = df_final['sold'] * df_final['price']
            
            total_rev = df_final['revenue'].sum()
            st.metric("Total Revenue Estimate", f"₹{total_rev:,.2f}")
            
            st.dataframe(df_final[['name', 'variant', 'sold', 'revenue']])
            
            if st.button("Submit for Approval 📤"):
                conn.execute("UPDATE inventory SET status=1 WHERE date=?", (date_str,))
                conn.commit()
                st.success("Submitted to Admin successfully!")
                st.session_state['wiz_idx'] = 0 # Reset

# --- ADMIN VIEW ---
def admin_view():
    st.sidebar.title("Admin Menu")
    menu = st.sidebar.radio("Go to", ["Dashboard", "Brand Manager", "Import Excel", "Settings"])

    if menu == "Settings":
        st.header("⚙️ Admin Settings")
        
        # 1. Change Admin Password (from previous step)
        with st.expander("👤 Change Admin Password", expanded=False):
            with st.form("change_pass_form"):
                current_user = st.session_state.get('user', 'admin')
                new_pass = st.text_input("New Admin Password", type="password")
                if st.form_submit_button("Update My Password"):
                    conn.execute("UPDATE users SET password=? WHERE username=?", (new_pass, current_user))
                    conn.commit()
                    st.success("Admin password updated.")

        # --- NEW: Change Shopkeeper PIN ---
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
    
    if menu == "Dashboard":
        st.header("📋 Approval Dashboard")
        
        # --- NEW: Export Current Inventory ---
        st.subheader("Export Data")
        
        # 1. Select Date to Export
        export_date = st.date_input("Select Date for Report", datetime.date.today())
        date_str = export_date.strftime("%Y-%m-%d")
        
        # 2. Fetch Data
        df_export = get_inventory(date_str)
        
        if not df_export.empty:
            # Calculate Sold/Revenue for the report
            df_export['sold'] = (df_export['opening'] + df_export['receipts']) - df_export['closing']
            df_export['revenue'] = df_export['sold'] * df_export['price']
            
            # Select clean columns for the CSV
            csv_data = df_export[['name', 'variant', 'opening', 'receipts', 'closing', 'sold', 'revenue', 'status']].to_csv(index=False).encode('utf-8')
            
            # 3. Download Button
            st.download_button(
                label="📥 Download Inventory as CSV",
                data=csv_data,
                file_name=f"inventory_report_{date_str}.csv",
                mime="text/csv"
            )
        else:
            st.info(f"No data found for {date_str}")
            
        st.divider()
        # ... (Existing Pending Approvals Logic follows here) ...
        # Find pending dates
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
