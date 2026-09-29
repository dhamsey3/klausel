#!/bin/sh
# One-shot MinIO setup, run by the minio-init service:
#  - private, versioned bucket (audit trail for GDPR Art. 5(2) accountability)
#  - optional least-privilege app user: can read/write/erase documents in that one
#    bucket, but cannot change versioning, policies or users. Created only when
#    MINIO_APP_PASSWORD is set; point AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY at it.
set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing "local/$S3_BUCKET"
mc anonymous set none "local/$S3_BUCKET"
mc version enable "local/$S3_BUCKET"

if [ -n "${MINIO_APP_PASSWORD:-}" ]; then
  sed "s/BUCKET/$S3_BUCKET/g" /klausel/app-policy.json > /tmp/policy.json
  mc admin policy create local klausel-app /tmp/policy.json
  mc admin user add local "$MINIO_APP_USER" "$MINIO_APP_PASSWORD"
  mc admin policy attach local klausel-app --user "$MINIO_APP_USER" 2>/dev/null \
    || echo "policy klausel-app already attached to $MINIO_APP_USER"
  echo "App user ready: $MINIO_APP_USER (bucket $S3_BUCKET only)"
fi
echo "Bucket ready: $S3_BUCKET"
