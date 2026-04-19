import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def get_drive_service():
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")

    if not creds_path:
        raise ValueError("GOOGLE_CREDENTIALS_PATH not set")

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

    return build("drive", "v3", credentials=creds)


def find_or_create_folder(folder_name: str):
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"Skipping Drive Folder Creation: {e}")
        return None

    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"

    results = service.files().list(q=query).execute()
    folders = results.get("files", [])

    if folders:
        return folders[0]["id"]

    folder = service.files().create(
        body={
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        },
        fields="id"
    ).execute()

    return folder["id"]


def upload_file(file_path, folder_id):
    if not folder_id:
        return "local_storage_only"
    
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"Skipping Drive Upload: {e}")
        return "local_storage_only"

    media = MediaFileUpload(file_path)

    file = service.files().create(
        body={
            "name": os.path.basename(file_path),
            "parents": [folder_id]
        },
        media_body=media,
        fields="id"
    ).execute()

    return file["id"]