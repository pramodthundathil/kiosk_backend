import hashlib
import zipfile
import os
from typing import Tuple, Optional
from django.core.exceptions import ValidationError

APK_MAGIC_BYTES = b"PK\x03\x04"

def compute_file_sha256_and_size(file_obj) -> Tuple[str, int]:
    """
    Computes the SHA-256 hex digest and total size in bytes of a file-like object
    by reading in 64KB chunks to avoid high memory consumption.
    Resets file pointer to the beginning after reading.
    """
    sha256 = hashlib.sha256()
    size = 0
    
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
        
    for chunk in file_obj.chunks(chunk_size=65536) if hasattr(file_obj, 'chunks') else iter(lambda: file_obj.read(65536), b""):
        if not chunk:
            break
        sha256.update(chunk)
        size += len(chunk)
        
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
        
    return sha256.hexdigest(), size


def validate_apk_file(file_obj, filename: Optional[str] = None) -> None:
    """
    Validates that the uploaded file is a valid Android APK archive.
    - Ensures file ends with .apk extension
    - Validates ZIP archive signature
    - Confirms presence of AndroidManifest.xml inside the archive
    """
    fname = filename or getattr(file_obj, 'name', '')
    if not fname.lower().endswith('.apk'):
        raise ValidationError(f"File '{fname}' must have a valid .apk file extension.")

    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
        
    header = file_obj.read(4) if not hasattr(file_obj, 'chunks') else next(file_obj.chunks(4))
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)

    if header != APK_MAGIC_BYTES:
        raise ValidationError("Uploaded file is not a valid ZIP/APK archive.")

    try:
        # Check that it is an intact zip file containing AndroidManifest.xml
        with zipfile.ZipFile(file_obj, 'r') as zf:
            namelist = zf.namelist()
            if 'AndroidManifest.xml' not in namelist:
                raise ValidationError("APK is invalid: missing AndroidManifest.xml inside archive.")
    except zipfile.BadZipFile:
        raise ValidationError("Uploaded file is a corrupted or incomplete APK archive.")
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Error inspecting APK archive: {str(e)}")
    finally:
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
