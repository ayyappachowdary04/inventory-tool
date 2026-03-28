import pdfplumber
import pandas as pd

CASE_CONVERSION = {
    1000: 9, 2000: 9,
    750: 12, 650: 12,
    375: 24,
    180: 48
}

SIZE_TO_VARIANT = {
    2000: "2L", 1000: "1L",
    750: "Q", 650: "Q",
    375: "P",
    180: "N"
}

def parse_pdf_receipt(file_bytes, db_brands_list):
    """
    Extracts inventory data from supplier PDF invoices.
    Returns a list of dicts: [{brand_id, brand_name, variant, qty, raw_pdf_brand}]
    """
    extracted_data = []

    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
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

                    for row in table[header_idx + 1:]:
                        if not row or len(row) < 3:
                            continue
                        raw_brand = str(row[col_brand]).strip()
                        raw_size  = str(row[col_size]).strip()
                        raw_cases = str(row[col_cases]).strip()

                        if "total" in raw_brand.lower():
                            continue

                        try:
                            size_ml = int(''.join(filter(str.isdigit, raw_size)))
                        except:
                            continue

                        try:
                            cases_str = raw_cases.split('/')[0].strip()
                            cases = float(cases_str)
                        except:
                            cases = 0

                        factor = CASE_CONVERSION.get(size_ml, 12)
                        total_qty = int(cases * factor)
                        if total_qty <= 0:
                            continue

                        matched_id = None
                        matched_name = None
                        for db_name, db_id in db_brands_list:
                            if db_name.lower() in raw_brand.lower():
                                matched_id = db_id
                                matched_name = db_name
                                break

                        if matched_id:
                            variant_code = SIZE_TO_VARIANT.get(size_ml)
                            if variant_code:
                                extracted_data.append({
                                    "brand_id": int(matched_id),
                                    "brand_name": matched_name,
                                    "variant": variant_code,
                                    "qty": total_qty,
                                    "raw_pdf_brand": raw_brand
                                })

    return extracted_data
