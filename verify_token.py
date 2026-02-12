import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def main():
    token_path = 'assets/creds/token.json'
    
    # 1. Check if file exists
    if not os.path.exists(token_path):
        print(f"❌ Error: {token_path} not found.")
        return

    print(f"✅ Found {token_path}")

    # 2. Load the credentials
    try:
        creds = Credentials.from_authorized_user_file(token_path)
    except Exception as e:
        print(f"❌ Error loading token: {e}")
        return

    # 3. Print the Scopes INSIDE the token
    print(f"🔍 Scopes in token: {creds.scopes}")

    # 4. Test the Refresh (The step that was failing in Cloud)
    if creds.expired and creds.refresh_token:
        print("🔄 Token expired, attempting refresh...")
        try:
            creds.refresh(Request())
            print("✅ Refresh successful!")
        except Exception as e:
            print(f"❌ Refresh FAILED: {e}")
            print("👉 CAUSE: The scopes in your code likely don't match this token.")
            return

    # 5. Test Actual Drive Access
    try:
        service = build('drive', 'v3', credentials=creds)
        results = service.files().list(pageSize=5).execute()
        files = results.get('files', [])
        print("✅ Drive API Connection Successful!")
        print(f"   Found {len(files)} files (Access verified).")
    except Exception as e:
        print(f"❌ Drive API Failed: {e}")

if __name__ == '__main__':
    main()