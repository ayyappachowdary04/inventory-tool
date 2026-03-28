import pandas as pd

# Diagnostic script for Excel import issues
def main(csv_file):
    try:
        # Read the CSV file
        data = pd.read_csv(csv_file)

        # Show the structure and details of the data
        print("Data Structure:")
        print(data.info())

        # Show column names
        print("\nColumn Names:")
        print(data.columns.tolist())

        # Example of brand matching attempts (this should be customized)
        # Assuming we have a list of valid brands
        valid_brands = ['BrandA', 'BrandB', 'BrandC']
        print("\nBrand Matching Attempts:")
        for brand in valid_brands:
            if brand in data['Brand'].values:
                print(f'Brand {brand} found in the data.')
            else:
                print(f'Brand {brand} NOT found in the data.')

    except Exception as e:
        print(f'Error occurred: {e}')

if __name__ == '__main__':
    # Replace 'your_file.csv' with the path to your CSV file
    main('your_file.csv')
