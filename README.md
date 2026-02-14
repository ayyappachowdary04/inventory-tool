Markdown
# Wine Shop Manager (Inventory Tool)

A streamlined, role-based inventory management system built with **Python** and **Streamlit**. Designed for wine shops to track daily stock, manage receipts, and generate sales reports with ease.

## Features

### **Shopkeeper Role (Daily Entry)**
* **Wizard Mode:** Step-by-step UI to enter closing stock for each brand.
* **Bulk Import:** Upload daily closing stock via Excel/CSV.
* **Validation:** Prevents entering closing stock higher than available stock.
* **Past Date Support:** Ability to submit closing reports for previous dates (e.g., catching up on weekends).
* **Final Preview:** Review sales summaries and revenue before submitting to Admin.

### **Admin Role (Management)**
* **Dashboard:** View daily sales, stock movement, and revenue totals.
* **Export Reports:** Download multi-sheet Excel reports (one sheet per day) for accounting.
* **Stock Intake:** Add new inventory manually, via Excel, or by **scanning PDF Receipts**.
* **Brand Manager:** Add new brands and update selling prices.
    * *Smart Import:* Fuzzy matching logic to detect typos and prevent duplicate brands.
* **System Settings:** Change passwords, backup database, and perform factory resets.

---

## 🛠️ Installation & Setup

### Prerequisites
* Python 3.8 or higher
* Git

### 1. Clone the Repository
```bash
git clone [https://github.com/akorrapati/inventory-tool.git](https://github.com/akorrapati/inventory-tool.git)
cd inventory-tool
2. Install Dependencies
Bash
pip install -r requirements.txt
3. Run the App
Bash
streamlit run wine_shop_app.py
The app will open in your browser at http://localhost:8501.
 
Default Credentials
When you run the app for the first time, a local SQLite database (wineshop.db) is created automatically with these default credentials:Note: You can change these passwords in the Admin > Settings tab.
 
Project Structure
Plaintext
inventory-tool/
├── wine_shop_app.py       # Main Application Code
├── requirements.txt       # Python Dependencies
├── wineshop.db            # SQLite Database (Created on first run)
├── README.md              # Documentation
└── .gitignore             # Files to ignore in Git
 
Configuration
Timezone
The app is configured to use IST (India Standard Time) by default for daily reporting. You can change this in wine_shop_app.py under the CONSTANTS section:
Python
# Change timedelta to your specific timezone offset
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
Requirements
The requirements.txt file should contain:
Plaintext
streamlit
pandas
openpyxl
pdfplumber
(Note: difflib and sqlite3 are built-in Python libraries and do not need to be listed.)
 
Smart Features Logic
1.	Fuzzy Matching (Brand Import):
o	When importing a Master Price List, the system uses difflib to find existing brands that are >85% similar to the new entry.
o	Example: Uploading "Blac Dog" will automatically update the existing "Black Dog" record instead of creating a duplicate.
2.	PDF Parsing:
o	The app uses pdfplumber to extract tables from supplier invoices.
o	It intelligently maps variants (e.g., "750ml" -> "Q") and converts case quantities into bottle counts based on industry standards (e.g., 1 Case of Nips = 48 bottles).
 
"Danger Zone"
Located in Admin > Settings, this section allows you to:
1.	Clear Inventory History: Wipes all sales data but keeps Brand Names & Prices intact (useful for starting a new financial year).
2.	Full Factory Reset: Deletes everything (Brands, Prices, Inventory). Use with caution!
 
Contributing
1.	Fork the repository.
2.	Create your feature branch (git checkout -b feature/AmazingFeature).
3.	Commit your changes (git commit -m 'Add some AmazingFeature').
4.	Push to the branch (git push origin feature/AmazingFeature).
5.	Open a Pull Request.
License
Distributed under the MIT License.

<img width="468" height="659" alt="image" src="https://github.com/user-attachments/assets/f6f6b055-a0c6-44bb-bc64-2495a0e1a00a" />
