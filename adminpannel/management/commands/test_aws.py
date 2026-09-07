from django.core.management.base import BaseCommand
from kiosk_backend.aws_utils import test_aws_credentials, test_s3_bucket_access

class Command(BaseCommand):
    help = "Tests AWS integration including IAM/STS credentials and S3 bucket read/write access."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Testing AWS STS credentials..."))
        cred_res = test_aws_credentials()
        if cred_res.get("success"):
            self.stdout.write(self.style.SUCCESS(f"✅ AWS Credentials Valid! Account: {cred_res.get('account')} | User ARN: {cred_res.get('arn')}"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ AWS Credentials Error: {cred_res.get('error')}"))
            return

        self.stdout.write(self.style.NOTICE("Testing S3 bucket read/write access..."))
        s3_res = test_s3_bucket_access()
        if s3_res.get("success"):
            self.stdout.write(self.style.SUCCESS(f"✅ S3 Bucket Access Verified! Bucket: {s3_res.get('bucket')} | Status: {s3_res.get('message')}"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ S3 Bucket Error for '{s3_res.get('bucket')}': {s3_res.get('error')}"))
