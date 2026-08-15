"""
File storage abstraction for uploaded materials.

Uses S3-compatible object storage (Cloudflare R2, Backblaze B2, AWS S3, or
anything else that speaks the S3 API) when credentials are present in the
environment - this is what production (Render) should use, since Render's
own disk is wiped on every deploy.

Falls back to saving files on local disk (the original behavior) when no
storage credentials are configured, so local development keeps working
with zero setup.

Set these in .env (or Render's environment settings) to enable cloud storage:
    STORAGE_ENDPOINT_URL   e.g. https://s3.us-west-004.backblazeb2.com (B2)
                            or https://<account_id>.r2.cloudflarestorage.com (R2)
    STORAGE_ACCESS_KEY_ID
    STORAGE_SECRET_ACCESS_KEY
    STORAGE_BUCKET_NAME
"""
import os
from flask import send_from_directory, redirect

STORAGE_ENDPOINT_URL = os.environ.get('STORAGE_ENDPOINT_URL')
STORAGE_ACCESS_KEY_ID = os.environ.get('STORAGE_ACCESS_KEY_ID')
STORAGE_SECRET_ACCESS_KEY = os.environ.get('STORAGE_SECRET_ACCESS_KEY')
STORAGE_BUCKET_NAME = os.environ.get('STORAGE_BUCKET_NAME')

USE_CLOUD_STORAGE = all([STORAGE_ENDPOINT_URL, STORAGE_ACCESS_KEY_ID, STORAGE_SECRET_ACCESS_KEY, STORAGE_BUCKET_NAME])
# Old name kept as an alias so nothing else needs to change.
USE_R2 = USE_CLOUD_STORAGE

_storage_client = None

def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        import boto3
        _storage_client = boto3.client(
            's3',
            endpoint_url=STORAGE_ENDPOINT_URL,
            aws_access_key_id=STORAGE_ACCESS_KEY_ID,
            aws_secret_access_key=STORAGE_SECRET_ACCESS_KEY,
            region_name='auto',
        )
    return _storage_client


def save_material_file(file_storage, filename, local_upload_folder):
    """Saves an uploaded file (a Werkzeug FileStorage) under the given
    generated filename. Storage location depends on whether cloud storage is configured."""
    if USE_CLOUD_STORAGE:
        client = _get_storage_client()
        client.upload_fileobj(file_storage.stream, STORAGE_BUCKET_NAME, filename)
    else:
        materials_dir = os.path.join(local_upload_folder, 'materials')
        os.makedirs(materials_dir, exist_ok=True)
        file_storage.save(os.path.join(materials_dir, filename))


def delete_material_file(filename, local_upload_folder):
    """Deletes a material file from wherever it's actually stored."""
    if USE_CLOUD_STORAGE:
        client = _get_storage_client()
        try:
            client.delete_object(Bucket=STORAGE_BUCKET_NAME, Key=filename)
        except Exception:
            pass
    else:
        try:
            os.remove(os.path.join(local_upload_folder, 'materials', filename))
        except OSError:
            pass


def material_file_response(filename, local_upload_folder, inline=False, download_name=None):
    """
    Returns a Flask response that serves the material file - either a
    redirect to a short-lived signed URL, or a direct local file response.
    """
    if USE_CLOUD_STORAGE:
        client = _get_storage_client()
        params = {'Bucket': STORAGE_BUCKET_NAME, 'Key': filename}
        disposition = 'inline' if inline else 'attachment'
        if download_name:
            disposition += f'; filename="{download_name}"'
        params['ResponseContentDisposition'] = disposition
        url = client.generate_presigned_url('get_object', Params=params, ExpiresIn=300)
        return redirect(url)
    else:
        return send_from_directory(
            os.path.join(local_upload_folder, 'materials'),
            filename,
            as_attachment=not inline,
            download_name=download_name
        )
