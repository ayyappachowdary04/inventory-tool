import pandas as pd
import os

def read_file(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    elif file_path.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file_path)
    else:
        raise ValueError('Unsupported file format.')

def diagnose_brand_matching(data, expected_brands):
    if 'Brand' not in data.columns:
        print('Brand column not found in the provided data.')
        return
    mismatches = data[~data['Brand'].isin(expected_brands)]
    if not mismatches.empty:
        print('Brand matching issues found:')
        print(mismatches)
    else:
        print('All brands match the expected values.')

if __name__ == '__main__':
    file_path = 'path/to/your/file.csv'  # Update this path
    expected_brands = ['BrandA', 'BrandB', 'BrandC']  # Update expected brands
    try:
        data = read_file(file_path)
        diagnose_brand_matching(data, expected_brands)
    except Exception as e:
        print(f'Error: {e}')