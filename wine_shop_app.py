import streamlit as st
import pandas as pd
import sqlite3
import datetime
import pdfplumber
import difflib  # UNCOMMENTED: Needed for fuzzy matching

# --- 1. SETUP & DATABASE (Global) ---
st.set_page_config(page_title="🍷 Wine Shop Manager", layout="wide")

# --- DATABASE SETUP (Cached & Safe) ---
@st.cache_resource
def get_db_connection():
    # 1. Create Connection
    conn = sqlite3.connect('wineshop.db', check_same_thread=False)
    c = conn.cursor()
    
    # 2. Schema Check (Auto-Fix Old Tables)
    try:
        c.execute("SELECT role FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("DROP TABLE IF EXISTS users")
    
    # 3. Create Tables
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS brands 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, is_alcohol BOOLEAN)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS prices 
                 (brand_id INTEGER, variant TEXT, price REAL, 
                  FOREIGN KEY(brand_id) REFERENCES brands(id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (date TEXT, brand_id INTEGER, variant TEXT, 
                  opening INTEGER, receipts INTEGER, closing INTEGER, 
                  status INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS price_audit 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, 
                  brand_id INTEGER, 
                  variant TEXT, 
                  old_price REAL, 
                  new_price REAL)''')
    
    # 4. Create Default Users
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('shopkeeper', '1234', 'shopkeeper')")
    
    conn.commit()
    return conn

# --- GLOBAL CONNECTION VARIABLE ---
# This ensures 'conn' is available to ALL functions below
conn = get_db_connection()

# --- 2. CONSTANTS ---
VARIANTS = ["2L", "1L", "Q", "P", "N"]

# --- TIMEZONE SETUP (IST: UTC +5:30) ---
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_india_date():
    """Returns the current date in India, regardless of server location."""
    return datetime.datetime.now(IST).date()

# --- PDF PARSING HELPER ---
def parse_pdf_receipt(uploaded_file, db_brands_list):
    """
    Extracts inventory data from the specific PDF format provided.
    Returns a DataFrame with columns: ['brand_id', 'variant', 'qty']
    """
    extracted_data = []
    
    # 1. Conversion Logic (Cases -> Bottles)
    case_conversion = {
        1000: 9, 2000: 9, 
        750: 12, 650: 12, 
        375: 24, 
        180: 48
    }
    
    # Map Size (ml) -> App Variant Code
    size_to_variant = {
        2000: "2L", 1000: "1L", 
        750: "Q", 650: "Q",
        375: "P", 
        180: "N"
    }

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            
            for table in tables:
                # Find header row
                header_idx = -1
                for i, row in enumerate(table):
                    row_text = [str(x).lower().replace('\n', ' ') for x in row if x]
                    if any("brand name" in x for x in row_text) and any("size" in x for x in row_text):
                        header_idx = i
                        break
                
                if header_idx != -1:
                    headers = [str(x).lower().replace('\n', ' ') for x in table[header_idx] if x]
                    
                    try:
                        col_brand = next(i for i, h in enumerate(headers) if "brand name" in h)
                        col_size  = next(i for i, h in enumerate(headers) if "size" in h)
                        col_cases = next(i for i, h in enumerate(headers) if "cases" in h)
                    except StopIteration:
                        continue 

                    # Process Data Rows
                    for row in table[header_idx+1:]:
                        if not row or len(row) < 3: continue
                        
                        raw_brand = str(row[col_brand]).strip()
                        raw_size  = str(row[col_size]).strip()
                        raw_cases = str(row[col_cases]).strip()
                        
                        if "total" in raw_brand.lower(): continue
                        
                        # 1. Parse Size
                        try:
                            size_ml = int(''.join(filter(str.isdigit, raw_size)))
                        except:
                            continue

                        # 2. Parse Qty (Strictly Cases)
                        try:
                            cases_str = raw_cases.split('/')[0].strip()
                            cases = float(cases_str)
                        except:
                            cases = 0
                            
                        # CALCULATION: Cases * Factor
                        factor = case_conversion.get(size_ml, 12) 
                        total_qty = int(cases * factor)
                        
                        if total_qty <= 0: continue

                        # 3. Match Brand Name
                        matched_id = None
                        matched_name = None
                        
                        for db_name, db_id in db_brands_list:
                            if db_name.lower() in raw_brand.lower():
                                matched_id = db_id
                                matched_name = db_name
                                break
                        
                        if matched_id:
                            variant_code = size_to_variant.get(size_ml)
                            if variant_code:
                                extracted_data.append({
                                    "brand_id": int(matched_id),
                                    "brand_name": matched_name,
                                    "variant": variant_code,
                                    "qty": total_qty,
                                    "raw_pdf_brand": raw_brand
                                })
    
    return pd.DataFrame(extracted_data)

# --- HELPER FUNCTIONS ---
def get_brands():
    return pd.read_sql("SELECT * FROM brands ORDER BY name", conn)

def get_inventory(date_str):
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
    # Notice we pass date_str twice now (once for the subquery, once for the main WHERE clause)
    return pd.read_sql(query, conn, params=(date_str, date_str))

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
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username='shopkeeper'")
            result = cur.fetchone()
            
            if result and result[0] == pin:
                st.session_state['role'] = 'shopkeeper'
                st.session_state['logged_in'] = True  # <--- FIXED: Set logged_in to True
                st.rerun()
            else:
                st.error("Invalid PIN")
    else:
        username = st.text_input("Username", value="admin")
        pwd = st.text_input("Enter Password", type="password")
        
        if st.button("Login"):
            cur = conn.cursor()
            cur.execute("SELECT password FROM users WHERE username=?", (username,))
            result = cur.fetchone()
            
            if result and result[0] == pwd:
                st.session_state['role'] = 'admin'
                st.session_state['user'] = username
                st.session_state['logged_in'] = True # <--- FIXED: Set logged_in to True
                st.rerun()
            else:
                st.error("Invalid Username or Password")

# --- SHOPKEEPER VIEW (WIZARD) ---
def shopkeeper_view():
    # --- LOGOUT BUTTON ---
    st.sidebar.title("Actions")
    if st.sidebar.button("🚪 Logout", key="shop_logout"):
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.rerun()

    st.markdown("### 🏪 Daily Closing Entry")
    st.info("ℹ️ Workflow: Select a date, enter closing stock counts, review the totals, and submit to Admin.")
    
    # 1. DATE SELECTION (Fixed: Uses IST & Allows Past Dates)
    current_ist = get_india_date() # <--- Uses India Time
    
    date = st.date_input(
        "Select Date", 
        current_ist, 
        max_value=current_ist # Blocks future dates based on India time
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
        # TAB 1: MANUAL WIZARD
        # ============================================================
        with tab_wiz:
            st.markdown("""
            **Instructions:**
            * Use **Search** to jump to a specific brand.
            * **Validation:** You cannot enter a number higher than the available stock.
            """)
            st.divider()
            
            brands = sorted(df['name'].unique())
            
            if 'wiz_idx' not in st.session_state: st.session_state['wiz_idx'] = 0
            if st.session_state['wiz_idx'] >= len(brands): st.session_state['wiz_idx'] = 0
            
            # --- SEARCH BAR ---
            current_brand_name = brands[st.session_state['wiz_idx']]
            selected_brand = st.selectbox(
                "🔍 Search / Jump to Brand:", 
                brands, 
                index=st.session_state['wiz_idx']
            )
            
            if selected_brand != current_brand_name:
                st.session_state['wiz_idx'] = list(brands).index(selected_brand)
                st.rerun()

            # --- RENDER FORM ---
            idx = st.session_state['wiz_idx']
            current_brand = brands[idx]
            brand_rows = df[df['name'] == current_brand]
            
            st.info(f"Brand {idx + 1} of {len(brands)}")
            st.markdown(f"## 🍾 {current_brand}")
            
            total_brand_stock = (brand_rows['opening'] + brand_rows['receipts']).sum()
            
            if total_brand_stock == 0:
                st.warning(f"⚠️ No stock available for {current_brand} (Opening + Receipts = 0).")
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
                    
                    for _, row in brand_rows.iterrows():
                        v = row['variant']
                        max_val = row['opening'] + row['receipts']
                        
                        if max_val > 0:
                            has_visible_variants = True
                            st.markdown(f"**{v}** (Available: {max_val})")
                            
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
                            updates[(row['brand_id'], v)] = row['closing']

                    if not has_visible_variants:
                        st.caption("No variants have active stock.")

                    st.divider()
                    col_prev, col_next = st.columns([1, 1])
                    go_prev = col_prev.form_submit_button("⬅️ Previous")
                    go_next = col_next.form_submit_button("Next ➡️")
                    
                    if go_prev or go_next:
                        for (bid, var), cl_val in updates.items():
                            conn.execute(
                                "UPDATE inventory SET closing=? WHERE date=? AND brand_id=? AND variant=?",
                                (cl_val, date_str, bid, var)
                            )
                        conn.commit()
                        
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
        # TAB 2: IMPORT EXCEL
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

                    if file_ext == 'csv': data_dict['Default'] = pd.read_csv(uploaded_file)
                    else: data_dict = pd.read_excel(uploaded_file, sheet_name=None)
                    
                    sheet_options = list(data_dict.keys())
                    default_idx = 0
                    for i, s_name in enumerate(sheet_options):
                        if date.strftime("%d") in s_name or date.strftime("%b") in s_name:
                            default_idx = i
                            
                    selected_sheet = st.selectbox("Select Sheet", sheet_options, index=default_idx)
                    
                    if st.button("Process Import"):
                        df_imp = data_dict[selected_sheet]
                        df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
                        
                        variant_map = {
                            "2l": "2L", "2000ml": "2L", "1l": "1L", "1000ml": "1L", "full": "1L",
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
                            match_count = 0
                            db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                            brand_map = {name.lower().strip(): bid for bid, name in zip(db_brands['id'], db_brands['name'])}
                            
                            brand_col = df_imp.columns[0]
                            for c in df_imp.columns:
                                if 'brand' in c or 'name' in c or 'item' in c: brand_col = c; break
                            
                            for _, row in df_imp.iterrows():
                                file_brand = str(row[brand_col]).strip()
                                bid = brand_map.get(file_brand.lower())
                                if bid:
                                    for col_name, sys_var in found_maps.items():
                                        try:
                                            val = row[col_name]
                                            closing_qty = int(float(val))
                                        except: closing_qty = 0
                                        conn.execute("""
                                            UPDATE inventory SET closing = ? 
                                            WHERE date = ? AND brand_id = ? AND variant = ?
                                        """, (closing_qty, date_str, bid, sys_var))
                                    match_count += 1
                            conn.commit()
                            st.success(f"✅ Imported {match_count} brands!")
                except Exception as e:
                    st.error(f"Import Error: {e}")

        # ============================================================
        # TAB 3: FINAL PREVIEW
        # ============================================================
        with tab_preview:
            st.subheader("📊 Final Daily Report")
            df['available'] = df['opening'] + df['receipts']
            df['sold'] = df['available'] - df['closing']
            df['item_revenue'] = df['sold'] * df['price']
            
            negatives = df[df['sold'] < 0]
            if not negatives.empty:
                st.error("❌ ERROR: You have entered Closing Stock > Available Stock.")
                st.dataframe(negatives[['name', 'variant', 'available', 'closing', 'sold']])
                st.stop()

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

            p_open.columns = pd.MultiIndex.from_product([['Opening (Inc Rcpt)'], p_open.columns])
            p_close.columns = pd.MultiIndex.from_product([['Closing Stock'], p_close.columns])
            p_sold.columns = pd.MultiIndex.from_product([['Sales'], p_sold.columns])

            final_df = pd.concat([p_open, p_close, p_sold], axis=1)
            final_df[('Sales', 'Revenue (₹)')] = revenue_series
            final_df = final_df.fillna(0)

            display_df = final_df.copy()
            display_df.columns = ['_'.join(col).strip() for col in display_df.columns.values]

            st.dataframe(final_df, use_container_width=True, height=600)
            
            total_rev = df['item_revenue'].sum()
            st.metric("💰 Total Shop Revenue", f"₹ {total_rev:,.2f}")
            
            if st.button("✅ Submit Final Report to Admin", type="primary"):
                conn.execute("UPDATE inventory SET status=1 WHERE date=?", (date_str,))
                conn.commit()
                st.balloons()
                st.success("Report Submitted Successfully!")
# --- ADMIN VIEW ---
def admin_view():
    st.sidebar.title("Admin Menu")
    
    # --- LOGOUT BUTTON ---
    if st.sidebar.button("🚪 Logout", key="admin_logout"):
        st.session_state['logged_in'] = False
        st.session_state['role'] = None
        st.session_state['user'] = None
        st.rerun()
        
    st.sidebar.divider()
    menu = st.sidebar.radio("Go to", ["Dashboard", "🚚 Stock Intake", "Brand Manager", "Import Excel", "Settings"])
    
    # --- 1. DASHBOARD ---
    if menu == "Dashboard":
        st.header("📊 Sales Dashboard")
        
        st.subheader("📅 Download Reports")
        col_d1, col_d2 = st.columns(2)
        
        # IST DATE USED HERE
        current_ist = get_india_date() 
        
        with col_d1:
            start_date = st.date_input("From Date", current_ist)
        with col_d2:
            end_date = st.date_input("To Date", current_ist)
        
        if start_date > end_date:
            st.error("Error: 'From Date' must be before 'To Date'.")
        else:
            delta = end_date - start_date
            date_list = [start_date + datetime.timedelta(days=i) for i in range(delta.days + 1)]
            
            st.info(f"Selected Range: {len(date_list)} days")

            def get_formatted_daily_df(target_date_str):
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
                df = pd.read_sql(query, conn, params=(target_date_str, target_date_str))
                
                if df.empty: return None
                
                df['available'] = df['opening'] + df['receipts']
                df['sold'] = df['available'] - df['closing']
                df['revenue'] = df['sold'] * df['price']
                
                variants_order = ["2L", "1L", "Q", "P", "N"]
                
                def make_pivot(val_col):
                    p = df.pivot_table(index='name', columns='variant', values=val_col, aggfunc='sum').fillna(0)
                    for v in variants_order:
                        if v not in p.columns: p[v] = 0
                    return p[variants_order]

                p_open = make_pivot('available')
                p_close = make_pivot('closing')
                p_sold = make_pivot('sold')
                
                rev_series = df.groupby('name')['revenue'].sum()
                
                p_open.columns = pd.MultiIndex.from_product([['1. Opening (Inc. Rcpts)'], p_open.columns])
                p_close.columns = pd.MultiIndex.from_product([['2. Closing Stock'], p_close.columns])
                p_sold.columns = pd.MultiIndex.from_product([['3. Sales Units'], p_sold.columns])
                
                final_df = pd.concat([p_open, p_close, p_sold], axis=1)
                
                final_df[('3. Sales Units', 'Total Revenue (₹)')] = rev_series
                final_df = final_df.fillna(0)
                
                totals = final_df.sum(numeric_only=True)
                final_df.loc['TOTAL'] = totals
                
                return final_df

            if st.button("📥 Generate Multi-Sheet Excel Report"):
                import io
                output = io.BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    days_with_data = 0
                    for d in date_list:
                        d_str = d.strftime("%Y-%m-%d")
                        sheet_name = d.strftime("%b %d")
                        daily_df = get_formatted_daily_df(d_str)
                        if daily_df is not None:
                            daily_df.to_excel(writer, sheet_name=sheet_name)
                            days_with_data += 1
                    
                    if days_with_data == 0:
                        pd.DataFrame({"Message": ["No Data Found"]}).to_excel(writer, sheet_name="No Data")

                data_xlsx = output.getvalue()
                filename = f"Sales_Report_{start_date}_to_{end_date}.xlsx"
                
                st.download_button(
                    label="⬇️ Download Excel File (.xlsx)",
                    data=data_xlsx,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                if days_with_data > 0:
                    st.success(f"✅ Report Ready! Includes TOTALS for {days_with_data} days.")
                else:
                    st.warning("⚠️ No data found for selected range.")

        st.divider()
        st.subheader("📈 Quick Look: Today's Stats")
        
        # IST DATE USED HERE FOR "TODAY'S STATS"
        today_str = get_india_date().strftime("%Y-%m-%d")
        
        today_df = get_formatted_daily_df(today_str)
        
        if today_df is not None:
            display_df = today_df.copy()
            display_df.columns = ['_'.join(col).strip() for col in display_df.columns.values]
            st.dataframe(display_df, height=400, use_container_width=True)
            
            total_rev = today_df.loc['TOTAL', ('3. Sales Units', 'Total Revenue (₹)')]
            st.metric("Today's Total Revenue", f"₹ {total_rev:,.2f}")
        else:
            st.info("No data available for today yet.")
            
    # --- 2. STOCK INTAKE (RECEIPTS) ---
    elif menu == "🚚 Stock Intake":
        st.header("🚚 Add New Stock (Receipts)")
        
        # IST DATE USED HERE
        date_in = st.date_input("Date of Receipt", get_india_date())
        
        date_str = date_in.strftime("%Y-%m-%d")
        
        if st.button("Load / Refresh Inventory for Date"):
            initialize_day(date_str)
            st.session_state['stock_date'] = date_str
            st.success(f"Inventory initialized for {date_str}")
            st.rerun()

        def safe_save_receipt(date_val, bid, var, qty):
            cur = conn.execute("""
                UPDATE inventory 
                SET receipts = receipts + ? 
                WHERE date = ? AND brand_id = ? AND variant = ?
            """, (qty, date_val, bid, var))
            
            if cur.rowcount == 0:
                conn.execute("""
                    INSERT INTO inventory (date, brand_id, variant, opening, receipts, closing, status)
                    VALUES (?, ?, ?, 0, ?, 0, 0)
                """, (date_val, bid, var, qty))
                return 1 
            return 1 

        if 'stock_date' in st.session_state and st.session_state['stock_date'] == date_str:
            
            tab_manual, tab_excel, tab_pdf = st.tabs(["✋ Manual Entry", "📂 Import Excel", "📄 Import PDF"])
            
            # TAB 1: MANUAL ENTRY
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
                        
                        if st.form_submit_button("💾 Save Receipts"):
                            for v, qty in input_vals.items():
                                cur = conn.execute("UPDATE inventory SET receipts=? WHERE date=? AND brand_id=? AND variant=?",
                                                     (qty, date_str, bid, v))
                                if cur.rowcount == 0:
                                    conn.execute("""
                                        INSERT INTO inventory (date, brand_id, variant, opening, receipts, closing, status)
                                        VALUES (?, ?, ?, 0, ?, 0, 0)
                                    """, (date_str, bid, v, qty))
                            conn.commit()
                            st.success(f"Updated stock receipts for {brand_sel}!")
                            st.rerun()

            # TAB 2: EXCEL IMPORT
            with tab_excel:
                st.subheader("📂 Bulk Import Receipts")
                uploaded_file = st.file_uploader("Upload Excel/CSV", type=["xlsx", "xls", "csv"], key="rec_excel")
                
                if uploaded_file:
                    if st.button("🚀 Process Import"):
                        try:
                            file_ext = uploaded_file.name.split('.')[-1].lower()
                            if file_ext == 'csv': df_imp = pd.read_csv(uploaded_file)
                            else: df_imp = pd.read_excel(uploaded_file)
                            
                            df_imp.columns = df_imp.columns.astype(str).str.strip().str.lower()
                            
                            variant_map = {
                                "2l": "2L", "1l": "1L", "q": "Q", "750ml": "Q", 
                                "p": "P", "375ml": "P", "n": "N", "180ml": "N"
                            }
                            found_maps = {c: variant_map[k] for c in df_imp.columns for k in variant_map if k in c}
                            
                            if not found_maps:
                                st.error("❌ No size columns found.")
                            else:
                                db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                                brand_map = {name.lower().strip(): bid for bid, name in zip(db_brands['id'], db_brands['name'])}
                                
                                brand_col = df_imp.columns[0]
                                for c in df_imp.columns:
                                    if 'brand' in c or 'name' in c: brand_col = c; break
                                
                                count = 0
                                for _, row in df_imp.iterrows():
                                    file_brand = str(row[brand_col]).strip()
                                    bid = brand_map.get(file_brand.lower())
                                    if bid:
                                        for col, var in found_maps.items():
                                            try: qty = int(float(row[col]))
                                            except: qty = 0
                                            if qty > 0:
                                                safe_save_receipt(date_str, bid, var, qty)
                                        count += 1
                                conn.commit()
                                st.success(f"✅ Successfully imported {count} brands!")
                                st.balloons()
                        except Exception as e:
                            st.error(f"Error: {e}")

            # TAB 3: PDF IMPORT
            with tab_pdf:
                st.subheader("📄 Import from PDF")
                uploaded_pdf = st.file_uploader("Upload Receipt PDF", type=["pdf"], key="pdf_upload")
                
                if 'pdf_data' not in st.session_state: st.session_state['pdf_data'] = None

                if uploaded_pdf:
                    if st.button("🔍 Process PDF"):
                        try:
                            db_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                            db_brands_list = sorted(list(zip(db_brands['name'], db_brands['id'])), key=lambda x: len(x[0]), reverse=True)
                            
                            df_extracted = parse_pdf_receipt(uploaded_pdf, db_brands_list)
                            
                            if df_extracted.empty:
                                st.error("❌ No data found.")
                                st.session_state['pdf_data'] = None
                            else:
                                st.success(f"✅ Found {len(df_extracted)} items.")
                                st.session_state['pdf_data'] = df_extracted
                        except Exception as e:
                            st.error(f"Error: {e}")

                if st.session_state['pdf_data'] is not None:
                    st.dataframe(st.session_state['pdf_data'][['brand_name', 'variant', 'qty']])
                    
                    if st.button("🚀 Save to Database", type="primary"):
                        update_count = 0
                        df_save = st.session_state['pdf_data']
                        for _, row in df_save.iterrows():
                            safe_save_receipt(date_str, row['brand_id'], row['variant'], row['qty'])
                            update_count += 1
                        
                        conn.commit()
                        st.session_state['pdf_data'] = None
                        st.balloons()
                        st.success(f"Saved {update_count} items!")
                        st.rerun()

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
        **Purpose:** Add new brands or update selling prices.
        * **Duplicate Protection:** Ignores spaces and capitalization.
        """)
        
        with st.expander("➕ Add New Brand Manually"):
            new_brand_raw = st.text_input("New Brand Name")
            
            if st.button("Add Brand"):
                if new_brand_raw:
                    clean_name = " ".join(new_brand_raw.split()).title()
                    search_key = clean_name.lower().replace(" ", "")
                    
                    existing = pd.read_sql(
                        "SELECT name FROM brands WHERE LOWER(REPLACE(name, ' ', '')) = ?", 
                        conn, params=(search_key,)
                    )
                    
                    if not existing.empty:
                        real_name = existing.iloc[0]['name']
                        st.error(f"❌ Duplicate prevented! Matches existing brand: **'{real_name}'**")
                    else:
                        try:
                            conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?)", (clean_name, True))
                            bid = conn.cursor().execute("SELECT last_insert_rowid()").fetchone()[0]
                            for v in VARIANTS:
                                conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))
                            conn.commit()
                            st.success(f"✅ Added '{clean_name}' successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding brand: {e}")

        st.divider()

        st.subheader("Edit Prices")
        brands_df = pd.read_sql("SELECT id, name FROM brands ORDER BY name", conn)
        
        if not brands_df.empty:
            brand_map = {row['name']: row['id'] for _, row in brands_df.iterrows()}
            sel_brand_name = st.selectbox("Select Brand to Edit", list(brand_map.keys()))
            
            if sel_brand_name:
                bid = brand_map[sel_brand_name]
                existing_prices = pd.read_sql("SELECT variant FROM prices WHERE brand_id=?", conn, params=(bid,))
                existing_vars = existing_prices['variant'].tolist()
                missing_vars = [v for v in VARIANTS if v not in existing_vars]
                
                if missing_vars:
                    for v in missing_vars:
                        conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))
                    conn.commit()
                
                prices_df = pd.read_sql("SELECT * FROM prices WHERE brand_id=?", conn, params=(bid,))
                
                with st.form("price_edit_form"):
                    st.write(f"Editing prices for: **{sel_brand_name}**")
                    cols = st.columns(len(VARIANTS))
                    input_values = {}
                    
                    for i, v_name in enumerate(VARIANTS):
                        row = prices_df[prices_df['variant'] == v_name]
                        current_val = 0.0
                        if not row.empty:
                            db_val = row.iloc[0]['price']
                            if db_val is not None:
                                current_val = float(db_val)
                        
                        with cols[i]:
                            new_val = st.number_input(
                                f"{v_name}", value=current_val, min_value=0.0, step=10.0, 
                                key=f"p_{bid}_{v_name}" 
                            )
                            input_values[v_name] = new_val
                    
                    st.caption("Prices are in Rupees (₹). Set to 0 if not sold.")
                    
                    if st.form_submit_button("💾 Save Updated Prices"):
                        # Get current timestamp in IST
                        now_str = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        
                        for var, new_price in input_values.items():
                            # 1. Fetch current (old) price
                            cur = conn.execute("SELECT price FROM prices WHERE brand_id=? AND variant=?", (bid, var))
                            res = cur.fetchone()
                            old_price = res[0] if (res and res[0] is not None) else 0.0
                            
                            # 2. Compare and Log if Changed
                            if new_price != old_price:
                                conn.execute("UPDATE prices SET price=? WHERE brand_id=? AND variant=?", (new_price, bid, var))
                                conn.execute("INSERT INTO price_audit (timestamp, brand_id, variant, old_price, new_price) VALUES (?, ?, ?, ?, ?)",
                                             (now_str, bid, var, old_price, new_price))
                                
                        conn.commit()
                        st.success(f"✅ Prices updated for {sel_brand_name}!")
                        st.rerun()
                        
        else:
            st.info("No brands found.")

        # --- NEW: SHOW AUDIT HISTORY IN UI ---
        st.divider()
        st.subheader("📜 Price Change History")
        history_df = pd.read_sql("""
            SELECT pa.timestamp as "Date & Time", b.name as "Brand", pa.variant as "Size", 
                   pa.old_price as "Old Price (₹)", pa.new_price as "New Price (₹)"
            FROM price_audit pa 
            JOIN brands b ON pa.brand_id = b.id 
            ORDER BY pa.timestamp DESC LIMIT 50
        """, conn)
        
        if not history_df.empty:
            st.dataframe(history_df, use_container_width=True, hide_index=True)
        else:
            st.info("No price changes recorded yet.")

    # --- 4. IMPORT EXCEL ---
    elif menu == "Import Excel":
        st.header("📥 Import Master Price List")
        st.markdown("""
        **Purpose:** Upload your full brand list here to populate the system.
        * **Duplicate Protection:** Ignores spaces/case.
        * **Typo Detection:** Fixes small errors (e.g., "Blac Dog" -> "Black Dog").
        * **Price Rules:** Type `0` to set price to zero. Leave **Blank** to keep existing.
        """)
        
        uploaded_file = st.file_uploader("Upload Price List", type=["xlsx", "xls", "csv"])
        
        if uploaded_file:
            if st.button("🚀 Process Import"):
                try:
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    data_dict = {}
                    if file_ext == 'csv': data_dict['Default'] = pd.read_csv(uploaded_file)
                    else: data_dict = pd.read_excel(uploaded_file, sheet_name=None)
                    
                    existing_brands = pd.read_sql("SELECT id, name FROM brands", conn)
                    brand_map_strict = {
                        str(row['name']).lower().replace(" ", ""): row['id'] 
                        for _, row in existing_brands.iterrows()
                    }
                    existing_names_list = existing_brands['name'].tolist()
                    
                    total_brands_touched = 0
                    total_prices_updated = 0
                    typos_fixed = 0
                    
                    for sheet_name, df_imp in data_dict.items():
                        if df_imp.empty: continue
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
                        if not found_maps: continue
                        
                        brand_col = df_imp.columns[0]
                        for c in df_imp.columns:
                            if 'brand' in c or 'name' in c: brand_col = c; break
                        
                        st.write(f"Processing sheet: *{sheet_name}*...")
                        
                        for _, row in df_imp.iterrows():
                            raw_brand = str(row[brand_col]).strip()
                            if not raw_brand or raw_brand.lower() == 'nan': continue
                            
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
                                    conn.execute("INSERT INTO brands (name, is_alcohol) VALUES (?, ?)", (clean_name, True))
                                    bid = conn.cursor().execute("SELECT last_insert_rowid()").fetchone()[0]
                                    brand_map_strict[clean_name.lower().replace(" ", "")] = bid
                                    existing_names_list.append(clean_name)
                                    for v in VARIANTS:
                                        conn.execute("INSERT INTO prices (brand_id, variant, price) VALUES (?, ?, 0.0)", (bid, v))

                            total_brands_touched += 1

                            # --- STEP B: UPDATE PRICES ---
                            for col_name, sys_var in found_maps.items():
                                val = row[col_name]
                                try:
                                    if pd.isna(val) or str(val).strip() == '': continue
                                    new_price = float(val)
                                    
                                    if new_price >= 0:
                                        # 1. Fetch current (old) price
                                        cur = conn.execute("SELECT price FROM prices WHERE brand_id=? AND variant=?", (bid, sys_var))
                                        res = cur.fetchone()
                                        old_price = res[0] if (res and res[0] is not None) else 0.0
                                        
                                        # 2. Compare and Log if Changed
                                        if new_price != old_price:
                                            now_str = datetime.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                                            conn.execute("""
                                                UPDATE prices SET price = ? 
                                                WHERE brand_id = ? AND variant = ?
                                            """, (new_price, bid, sys_var))
                                            
                                            conn.execute("INSERT INTO price_audit (timestamp, brand_id, variant, old_price, new_price) VALUES (?, ?, ?, ?, ?)",
                                                         (now_str, bid, sys_var, old_price, new_price))
                                            total_prices_updated += 1
                                except: continue
                                    
                    conn.commit()
                    msg = f"✅ Import Complete!\n• Brands Processed: {total_brands_touched}\n• Prices Updated: {total_prices_updated}"
                    if typos_fixed > 0: msg += f"\n• 🪄 Auto-corrected {typos_fixed} typos."
                    st.success(msg)
                    st.balloons()
                except Exception as e:
                    st.error(f"Import Failed: {e}")

    # --- 5. SETTINGS ---
    elif menu == "Settings":
        st.header("⚙️ Admin Settings")
        
        with st.expander("👤 Change Admin Password", expanded=False):
            with st.form("change_pass_form"):
                current_user = st.session_state.get('user', 'admin')
                new_pass = st.text_input("New Admin Password", type="password")
                if st.form_submit_button("Update My Password"):
                    conn.execute("UPDATE users SET password=? WHERE username=?", (new_pass, current_user))
                    conn.commit()
                    st.success("Admin password updated.")

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
        try:
            with open("wineshop.db", "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="📥 Download Database Backup (.db)",
                data=db_bytes,
                file_name=f"wineshop_backup_{get_india_date()}.db",
                mime="application/octet-stream"
            )
        except Exception as e:
            st.error(f"Could not read database file: {e}")

        st.divider()
        st.subheader("⚠️ Danger Zone")
        
        with st.expander("🔥 Clear Inventory History (Keep Brands)", expanded=True):
            st.markdown("""
            **Action:** Deletes all daily counts (Opening, Closing, Sold).
            **Result:** Sales history is wiped, but Brands & Prices remain.
            """)
            with st.form("reset_inventory_form"):
                confirm_inv = st.checkbox("I confirm I want to delete all INVENTORY history.")
                if st.form_submit_button("Clear Inventory Data"):
                    if confirm_inv:
                        try:
                            conn.execute("DELETE FROM inventory")
                            conn.commit()
                            st.error("✅ Inventory history has been wiped.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.warning("Please check the confirmation box.")

        with st.expander("💀 Delete All Brands & Prices (Full Reset)", expanded=False):
            st.markdown("""
            **Action:** Deletes ALL Brand Names and their Prices.
            **Result:** The system will be completely empty (no products).
            """)
            with st.form("reset_brands_form"):
                confirm_brand = st.checkbox("I confirm I want to delete ALL BRANDS and PRICES.")
                if st.form_submit_button("Delete Brands & Prices"):
                    if confirm_brand:
                        try:
                            conn.execute("DELETE FROM inventory") 
                            conn.execute("DELETE FROM prices")
                            conn.execute("DELETE FROM brands")
                            conn.commit()
                            st.error("✅ System Wiped: All Brands, Prices, and Inventory deleted.")
                            st.toast("Master List Cleared.")
                        except Exception as e:
                            st.error(f"Error deleting brands: {e}")
                    else:
                        st.warning("Please check the confirmation box.")
# --- MAIN APP LOGIC ---
if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['user'] = None
        st.session_state['role'] = None

    if not st.session_state['logged_in']:
        login_screen()
    else:
        if st.session_state['role'] == 'admin':
            admin_view()
        else:
            shopkeeper_view()
