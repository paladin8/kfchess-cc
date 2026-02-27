import boto3

import config


client = boto3.client(
    's3',
    region_name=config.AWS_REGION,
    aws_access_key_id=config.AWS_ACCESS_KEY,
    aws_secret_access_key=config.AWS_SECRET_KEY,
)


def upload_data(bucket, key, data, **kwargs):
    client.put_object(Bucket=bucket, Key=key, Body=data, **kwargs)


def get_public_url(bucket, key):
    return 'https://s3-{region}.amazonaws.com/{bucket}/{key}'.format(
        region=config.AWS_REGION, bucket=bucket, key=key
    )


if __name__ == '__main__':
    upload_data('com-kfchess-public', 'test', 'test')
