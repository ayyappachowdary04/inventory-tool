import os
import pandas as pd

os.makedirs('sample_excels', exist_ok=True)

closing = pd.DataFrame({
    'Brand': ['Black Dog', 'Signature', 'Royal Stag'],
    '750ml': [12, 8, 5],
    '1L': [4, 10, 3],
    '2L': [0, 1, 0],
    'Pint': [2, 0, 1],
    'Nip': [0, 0, 0]
})
closing.to_excel('sample_excels/sample_closing_import.xlsx', index=False)

receipts = pd.DataFrame({
    'Brand': ['Black Dog', 'Signature', 'Royal Stag'],
    '750ml': [5, 0, 2],
    '1L': [1, 4, 0],
    '2L': [0, 0, 0],
    'Pint': [1, 2, 0],
    'Nip': [0, 0, 1]
})
receipts.to_excel('sample_excels/sample_receipts_import.xlsx', index=False)

brands = pd.DataFrame({
    'Brand': ['Black Dog', 'Signature', 'Royal Stag'],
    '750ml Price': [250.0, 220.0, 240.0],
    '1L Price': [480.0, 420.0, 460.0],
    '2L Price': [900.0, 850.0, 880.0],
    'Pint Price': [130.0, 120.0, 125.0],
    'Nip Price': [70.0, 65.0, 68.0]
})
brands.to_excel('sample_excels/sample_brands_import.xlsx', index=False)

print('Created files in sample_excels/')
