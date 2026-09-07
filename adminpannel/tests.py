from django.test import TestCase
from django.conf import settings
from kiosk_backend.aws_utils import (
    test_aws_credentials,
    test_s3_bucket_access,
    upload_file_to_s3,
    upload_large_file_to_s3,
    generate_presigned_upload_url,
    get_s3_client
)
import io

class AWSIntegrationTest(TestCase):
    def test_aws_settings_configured(self):
        """Verify that AWS settings are populated in Django configuration."""
        self.assertIsNotNone(settings.AWS_ACCESS_KEY_ID)
        self.assertEqual(settings.AWS_ACCESS_KEY_ID, "AKIAWLVNT2SPVODSQVXZ")
        self.assertIsNotNone(settings.AWS_SECRET_ACCESS_KEY)
        self.assertIsNotNone(settings.AWS_STORAGE_BUCKET_NAME)
        self.assertEqual(settings.AWS_STORAGE_BUCKET_NAME, "excelearthing-437377029279-ap-south-1-an")

    def test_large_file_upload_settings(self):
        """Verify settings configured for large file upload body limits."""
        self.assertEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 2147483648)
        self.assertEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 10485760)
        self.assertEqual(settings.AWS_S3_SIGNATURE_VERSION, "s3v4")

    def test_aws_sts_credentials(self):
        """Verify that AWS credentials can successfully authenticate with STS."""
        res = test_aws_credentials()
        self.assertTrue(res.get("success"), f"STS authentication failed: {res.get('error')}")
        self.assertIn("437377029279", res.get("account", ""))
        self.assertIn("arn:aws:iam::", res.get("arn", ""))

    def test_s3_bucket_read_write(self):
        """Verify that S3 bucket can read, write, and delete test objects."""
        res = test_s3_bucket_access()
        self.assertTrue(res.get("success"), f"S3 Bucket access failed: {res.get('error')}")

    def test_upload_file_to_s3_utility(self):
        """Test the upload_file_to_s3 helper function."""
        test_filename = "test_unit_upload.txt"
        file_content = b"Unit test content for AWS S3 upload"
        url = upload_file_to_s3(file_content, test_filename, content_type="text/plain")
        
        self.assertIsNotNone(url)
        self.assertIn("excelearthing-437377029279-ap-south-1-an", url)
        self.assertIn("test_unit_upload.txt", url)

        # Cleanup uploaded file
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_filename)

    def test_upload_large_file_to_s3_utility(self):
        """Test multipart transfer config for large file stream upload."""
        test_filename = "large_files/unit_test_stream.bin"
        # Simulate a 1MB stream (using bytes IO)
        large_data = io.BytesIO(b"0" * 1024 * 1024)
        url = upload_large_file_to_s3(large_data, test_filename, content_type="application/octet-stream")

        self.assertIsNotNone(url)
        self.assertIn("unit_test_stream.bin", url)

        # Cleanup
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=test_filename)

    def test_generate_presigned_upload_url(self):
        """Test generation of pre-signed S3 URL for direct client large uploads."""
        test_filename = "large_files/direct_upload.mp4"
        presigned_url = generate_presigned_upload_url(test_filename, content_type="video/mp4")

        self.assertIsNotNone(presigned_url)
        self.assertIn("excelearthing-437377029279-ap-south-1-an", presigned_url)
        self.assertIn("direct_upload.mp4", presigned_url)
        self.assertIn("X-Amz-Signature", presigned_url)
