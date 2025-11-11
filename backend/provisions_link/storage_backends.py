# backend/provisions_link/storage_backends.py

import os
from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    bucket_name = os.getenv('AWS_STATIC_BUCKET_NAME', 'provisions-link-static')
    location = 'static'
    default_acl = None  # ACLs disabled - using bucket policy instead
    file_overwrite = True
    querystring_auth = False


class MediaStorage(S3Boto3Storage):
    bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME', 'provisions-link-media')
    location = 'media'
    default_acl = None  # ACLs disabled - using bucket policy instead
    file_overwrite = False
    querystring_auth = False
