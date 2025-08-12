#!/usr/bin/env python3
"""
Gmail Token Regeneration Script
Generates a new Gmail OAuth token with the correct scopes for reading emails.
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Define the scopes we need
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://mail.google.com/'
]

def regenerate_gmail_token():
    """Regenerate Gmail OAuth token with correct scopes."""
    
    # Path to your client secret file
    client_secret_path = 'creds/client_secret_gmail.json'
    
    if not os.path.exists(client_secret_path):
        print(f"❌ Client secret file not found at {client_secret_path}")
        print("Please ensure the client_secret_gmail.json file is in the creds/ directory")
        return None
    
    print("🔐 Starting Gmail OAuth flow...")
    print(f"📋 Required scopes: {SCOPES}")
    
    # Create the flow using the client secrets file
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_path, 
        SCOPES
    )
    
    # Run the OAuth flow
    print("🌐 Opening browser for Gmail authorization...")
    print("⚠️  Please authorize access to Gmail in the browser window that opens")
    
    creds = flow.run_local_server(port=0)
    
    # Convert credentials to JSON format
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "universe_domain": getattr(creds, 'universe_domain', 'googleapis.com'),
        "account": "",
        "expiry": creds.expiry.isoformat() if creds.expiry else None
    }
    
    # Print the token for .env file
    token_json = json.dumps(token_data)
    
    print("\n✅ Successfully generated new Gmail OAuth token!")
    print("\n📝 Copy the following line to your .env file:")
    print("=" * 80)
    print(f"GMAIL_OAUTH_TOKEN='{token_json}'")
    print("=" * 80)
    
    # Also save to a file for backup
    backup_file = 'creds/gmail_token_new.json'
    with open(backup_file, 'w') as f:
        json.dump(token_data, f, indent=2)
    
    print(f"\n💾 Token also saved to: {backup_file}")
    print("\n🔄 Next steps:")
    print("1. Copy the GMAIL_OAUTH_TOKEN line above to your .env file")
    print("2. Replace the existing GMAIL_OAUTH_TOKEN value")
    print("3. Restart your events-handler service")
    print("4. Test with a new email to verify real content is fetched")
    
    return token_data

if __name__ == "__main__":
    print("🚀 Gmail Token Regeneration Tool")
    print("=" * 50)
    
    try:
        token = regenerate_gmail_token()
        if token:
            print("\n✨ Token regeneration completed successfully!")
        else:
            print("\n❌ Token regeneration failed!")
    except Exception as e:
        print(f"\n💥 Error during token regeneration: {e}")
        print("\nTroubleshooting:")
        print("- Ensure creds/client_secret_gmail.json exists")
        print("- Check your internet connection")
        print("- Make sure you have the google-auth-oauthlib package installed")