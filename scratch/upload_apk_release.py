#!/usr/bin/env python3
"""
CLI Tool to upload an Android APK release directly to AWS S3.
Uses multi-threaded parallel chunks with real-time upload progress.
Bypasses Cloudflare, Nginx, and Gunicorn upload limits.
"""

import os
import sys
import argparse
import hashlib
import boto3
from boto3.s3.transfer import TransferConfig
from dotenv import load_dotenv

def compute_sha256(filepath):
    sha = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Upload APK directly to AWS S3")
    parser.add_argument("--apk", default="../kiosk_mobile_app/kiosk-android-tv.apk", help="Path to APK file")
    parser.add_argument("--version", default="1.1.9", help="Release version name (e.g. 1.1.9)")
    parser.add_argument("--code", type=int, default=20, help="Release version code (e.g. 20)")
    args = parser.parse_args()

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(backend_dir, '.env')
    load_dotenv(env_path)

    apk_path = os.path.abspath(os.path.expanduser(args.apk))
    if not os.path.isfile(apk_path):
        print(f"Error: APK file not found at '{apk_path}'")
        sys.exit(1)

    file_size = os.path.getsize(apk_path)
    file_size_mb = file_size / (1024 * 1024)
    print(f"📦 APK File: {apk_path} ({file_size_mb:.2f} MB)")

    print("🔍 Computing SHA-256 checksum...")
    sha256 = compute_sha256(apk_path)
    print(f"   SHA-256: {sha256}")

    bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    region = os.environ.get('AWS_S3_REGION_NAME', 'ap-south-1')

    if not bucket or not access_key or not secret_key:
        print("Error: AWS credentials missing in .env file.")
        sys.exit(1)

    s3_key = f"media/apks/kiosk-android-tv-v{args.version}.apk"
    s3_storage_key = f"apks/kiosk-android-tv-v{args.version}.apk"

    s3 = boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com"
    )

    print(f"🚀 Uploading to s3://{bucket}/{s3_key}...")
    uploaded_bytes = 0
    def progress_callback(bytes_amount):
        nonlocal uploaded_bytes
        uploaded_bytes += bytes_amount
        percent = (uploaded_bytes / file_size) * 100
        mb_done = uploaded_bytes / (1024 * 1024)
        sys.stdout.write(f"\r   Progress: {percent:5.1f}% [{mb_done:5.1f} / {file_size_mb:5.1f} MB]")
        sys.stdout.flush()

    config = TransferConfig(
        multipart_threshold=8 * 1024 * 1024,
        max_concurrency=10,
        multipart_chunksize=8 * 1024 * 1024,
        use_threads=True
    )

    s3.upload_file(apk_path, bucket, s3_key, Callback=progress_callback, Config=config)
    print("\n✅ Upload complete!")

    presigned_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': s3_key},
        ExpiresIn=604800  # 7 days
    )

    print("\n" + "="*70)
    print("🎉 RELEASE READY FOR ADMIN PANEL")
    print("="*70)
    print(f"Version Name: {args.version}")
    print(f"Version Code: {args.code}")
    print(f"S3 File Key:  {s3_storage_key}")
    print(f"File Size:    {file_size} bytes ({file_size_mb:.2f} MB)")
    print(f"SHA-256:      {sha256}")
    print("\nDirect Download URL (paste into 'Alternative: Direct APK Download URL'):")
    print(presigned_url)
    print("="*70)

if __name__ == '__main__':
    main()
