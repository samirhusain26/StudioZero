from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import os

# Permissions to ask for
SCOPES = [
    'https://www.googleapis.com/auth/drive',        # <--- Changed from 'drive.file' to 'drive' (Full Access)
    'https://www.googleapis.com/auth/spreadsheets'
]

def main():
    # 1. Check for the client secret
    if not os.path.exists('assets/creds/client_secret.json'):
        print("❌ Error: assets/creds/client_secret.json not found!")
        return

    # 2. Open the browser to log in
    print("Opening browser...")
    flow = InstalledAppFlow.from_client_secrets_file(
        'assets/creds/client_secret.json', SCOPES)
    creds = flow.run_local_server(port=0)

    # 3. Save the resulting Key
    with open('assets/creds/token.json', 'w') as token:
        token.write(creds.to_json())
    
    print("\n✅ SUCCESS! Token saved to: assets/creds/token.json")
    print("👉 Open this file, copy the text, and put it in GitHub Secrets.")

if __name__ == '__main__':
    main()