import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os


# import variabales from config.py
from config import INVOICE_NINJA_API_KEY, INVOICE_NINJA_BASE_URL, INVOICE_NINJA_SECRET_KEY, SHEET_ID, STARTING_CELL, GOOGLE_SHEETS_CREDENTIALS_FILE


# Google Sheets setup
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
print(os.getcwd())
credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_FILE, scope)
gc = gspread.authorize(credentials)


def fetch_invoice_ninja_data(endpoint):
    all_data = []
    page = 1
    while True:
        url = f"{INVOICE_NINJA_BASE_URL}/{endpoint}?page={page}"
        headers = {'X-API-TOKEN': INVOICE_NINJA_API_KEY}
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Error fetching data: {response.status_code}, {response.text}")
            break

        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            break

        data = json_response.get('data', [])
        # Filter out records where is_deleted is True
        filtered_data = [record for record in data if not record.get('is_deleted', False) and record.get('status_id') != '5']
        all_data.extend(filtered_data)

        if 'meta' in json_response and 'pagination' in json_response['meta']:
            total_pages = json_response['meta']['pagination']['total_pages']
            if page >= total_pages:
                break
        page += 1

    return all_data


# Extract and concatenate attributes from a list of dictionaries (e.g., line_items)
def extract_line_items(line_items):
    attributes = ['attribute1', 'attribute2', 'attribute3']  # Replace with actual attribute names
    combined = {attr: [] for attr in attributes}

    for item in line_items:
        for attr in attributes:
            value = item.get(attr, '')
            combined[attr].append(str(value))

    for attr, values in combined.items():
        combined[attr] = ', '.join(values)

    return combined



# Flatten an individual entry based on its data type
def flatten_entry(entry, data_type):
    flat_entry = {'raw_json': json.dumps(entry)}  # Store the entire JSON object as a string in the first column

    # Map top-level attributes directly
    for key, value in entry.items():
        if not isinstance(value, (list, dict)):
            flat_entry[key] = value

    
    # Map top-level attributes directly
    for key, value in entry.items():
        if not isinstance(value, (list, dict)):
            flat_entry[key] = value

    # Handling 'paymentables'
    for i in range(4):
        if i < len(entry.get('paymentables', [])):
            paymentable = entry['paymentables'][i]
            for p_key, p_value in paymentable.items():
                flat_entry[f'paymentable_{i}_{p_key}'] = p_value
        else:
            flat_entry.update({f'paymentable_{i}_{p_key}': '' for p_key in ['id', 'invoice_id', 'amount', 'refunded', 'created_at', 'updated_at', 'archived_at']})


    # Handling 'documents' for invoices
    if data_type == 'invoices' and 'documents' in entry:
        for i, document in enumerate(entry['documents']):
            for doc_key, doc_value in document.items():
                flat_entry[f'document_{i}_{doc_key}'] = doc_value
            # Fill in blank values for missing documents
            for j in range(i + 1, 4):
                flat_entry.update({f'document_{j}_{doc_key}': '' for doc_key in document.keys()})

    # # Handling 'documents'
    # for i in range(4):
    #     if i < len(entry.get('documents', [])):
    #         document = entry['documents'][i]
    #         for d_key, d_value in document.items():
    #             flat_entry[f'document_{i}_{d_key}'] = d_value
    #     else:
    #         flat_entry.update({f'document_{i}_{d_key}': '' for d_key in ['id', 'url', 'name', 'type', 'size', 'updated_at', 'created_at']})  # List all keys in documents here



    if data_type == 'invoices':
        if 'line_items' in entry:
            line_items_combined = extract_line_items(entry['line_items'])
            for key, value in line_items_combined.items():
                flat_entry[f'line_item_{key}'] = value

    if 'contacts' in entry and entry['contacts']:
        first_contact = entry['contacts'][0]
        for contact_key, contact_value in first_contact.items():
            flat_entry[f'contact_{contact_key}'] = contact_value

    return flat_entry




# Flatten JSON object based on its data type
def flatten_json(json_obj, data_type):
    return [flatten_entry(entry, data_type) for entry in json_obj]

# Update Google Sheet with flattened data
def update_google_sheet(sheet_name, data):
    flattened_data = flatten_json(data, sheet_name.split('.')[1])

    sheet = gc.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(sheet_name)

    if not flattened_data:
        print(f"No data to update for {sheet_name}")
        return

    headers = list(flattened_data[0].keys()) if flattened_data else []
    rows = [list(item.values()) for item in flattened_data] if flattened_data else []

    try:
        worksheet.update(STARTING_CELL, [headers] + rows)
    except Exception as e:
        print(f"Error updating sheet {sheet_name}: {e}")

# Main function to execute the script
def main():
    customers = fetch_invoice_ninja_data('clients')
    update_google_sheet('ninja.customers.auto', customers)

    invoices = fetch_invoice_ninja_data('invoices')
    update_google_sheet('ninja.invoices.auto', invoices)

    payments = fetch_invoice_ninja_data('payments')
    update_google_sheet('ninja.payments.auto', payments)

if __name__ == "__main__":
    main()