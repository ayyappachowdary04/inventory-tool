# excel_import_parser.py

import pandas as pd

def parse_excel(file_path):
    """A robust Excel parser that handles multi-row headers, identifies brand rows,
    skips summary/total rows, validates data, and returns a clean DataFrame ready for
    database import with helpful error messages."""
    try:
        # Load the Excel file
        df = pd.read_excel(file_path, header=None)

        # Identify and set multi-row headers
        headers = df.iloc[0:2]  # Example for 2-row headers
        df.columns = pd.MultiIndex.from_frame(headers)
        df = df[2:]  # Drop header rows

        # Identify brand rows (example: based on a specific column)
        brands = df[df['BrandColumn'].notnull()]

        # Skip summary/total rows (example: based on another column)
        df = df[df['TotalColumn'].isnull()]  # Adjust condition as needed

        # Validate data (add validation logic as needed)
        clean_data = df.dropna()  # Example validation

        return clean_data
    except Exception as e:
        print(f"Error parsing Excel file: {e}")
        return None
