from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.storage import default_storage
import os

class Command(BaseCommand):
    help = 'Uploads all local media files from MEDIA_ROOT to the default storage backend (AWS S3).'

    def handle(self, *args, **options):
        media_root = str(settings.MEDIA_ROOT)
        if not os.path.exists(media_root):
            self.stdout.write(self.style.WARNING(f'MEDIA_ROOT directory does not exist: {media_root}'))
            return

        self.stdout.write(self.style.NOTICE(f'Scanning {media_root} for local media files...'))
        self.stdout.write(f'Target Storage Backend: {settings.STORAGES["default"]["BACKEND"]}')

        uploaded_count = 0
        skipped_count = 0

        for root, dirs, files in os.walk(media_root):
            for f in files:
                if f.startswith('.'):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, media_root)

                if default_storage.exists(rel_path):
                    self.stdout.write(self.style.SUCCESS(f'[EXISTS] {rel_path}'))
                    skipped_count += 1
                else:
                    self.stdout.write(f'[UPLOADING] {rel_path}...')
                    try:
                        with open(full_path, 'rb') as fp:
                            default_storage.save(rel_path, fp)
                        self.stdout.write(self.style.SUCCESS(f'[SUCCESS] Uploaded {rel_path}'))
                        uploaded_count += 1
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'[FAILED] {rel_path}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nFinished S3 Media Sync! Uploaded: {uploaded_count}, Existed/Skipped: {skipped_count}'
        ))
