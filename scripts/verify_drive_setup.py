
import os
import sys
from dotenv import load_dotenv

# Add project root to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.drive_utils import get_drive_service, upload_markdown_file

def verify_drive_setup():
    load_dotenv()
    
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
    
    print(f"Checking configuration...")
    print(f"GOOGLE_CREDENTIALS_PATH: {creds_path}")
    print(f"GOOGLE_DRIVE_FOLDER_ID: {folder_id}")
    
    if not creds_path or not os.path.exists(creds_path):
        print("ERROR: Credentials path invalid or file does not exist.")
        return
        
    if not folder_id:
        print("ERROR: Folder ID is missing.")
        return

    try:
        print("\nAttempting to authenticate using ADC (ignoring GOOGLE_CREDENTIALS_PATH for this test)...")
        # Pass None to force ADC check in drive_utils.py
        service = get_drive_service(None) 
        print("Authentication successful!")
        
        print("\nAttempting to upload a test file...")
        test_content = "# Verification\n\nThis is a test file to verify the Google Drive integration for Literature Search."
        file_id = upload_markdown_file(service, folder_id, "INTEGRATION_TEST.md", test_content)
        print(f"Test file uploaded successfully! File ID: {file_id}")
        
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_drive_setup()
