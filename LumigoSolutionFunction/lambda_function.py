import json
import boto3
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
import urllib3
import os

lambda_client = boto3.client('lambda')
sns = boto3.client('sns')

headers = {
    "Authorization": "Bot " + os.environ["BotSecret"]
}

PUBLIC_KEY = os.environ["PUBLIC_KEY"] # found on Discord Application -> General Information page
PING_PONG = {"type": 1}
RESPONSE_TYPES =  { 
                    "PONG": 1, 
                    "ACK_NO_SOURCE": 2, 
                    "MESSAGE_NO_SOURCE": 3, 
                    "MESSAGE_WITH_SOURCE": 4, 
                    "ACK_WITH_SOURCE": 5
                  }


def verify_signature(event):
    raw_body = event.get("rawBody")
    auth_sig = event['params']['header'].get('x-signature-ed25519')
    auth_ts  = event['params']['header'].get('x-signature-timestamp')
    
    message = auth_ts.encode() + raw_body.encode()
    verify_key = VerifyKey(bytes.fromhex(PUBLIC_KEY))
    verify_key.verify(message, bytes.fromhex(auth_sig)) # raises an error if unequal

def ping_pong(body):
    if body.get("type") == 1:
        return True
    return False

def create_presigned_post(bucket_name, object_name,
                          fields=None, conditions=None, expiration=3600):
    """Generate a presigned URL S3 POST request to upload a file

    :param bucket_name: string
    :param object_name: string
    :param fields: Dictionary of prefilled form fields
    :param conditions: List of conditions to include in the policy
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Dictionary with the following keys:
        url: URL to post to
        fields: Dictionary of form fields and values to submit with the POST
    :return: None if error.
    """

    # Generate a presigned S3 POST URL
    s3_client = boto3.client('s3')
    try:
        response = s3_client.generate_presigned_post(bucket_name,
                                                     object_name,
                                                     Fields=fields,
                                                     Conditions=conditions,
                                                     ExpiresIn=expiration)
    except ClientError as e:
        logging.error(e)
        return None

    # The response contains the presigned URL and required fields
    return response
    
def lambda_handler(event, context):
    print(f"event {event}") # debug print
    # verify the signature
    try:
        verify_signature(event)
    except Exception as e:
        raise Exception(f"[UNAUTHORIZED] Invalid request signature: {e}")


    # check if message is a ping
    body = event.get('body-json')
    if ping_pong(body):
        return PING_PONG
    # Add author of attachment info
    if body.get('data').get('name') == 'sync':
        url = 'https://discord.com/api/v8/channels/' + body.get('channel_id') + '/messages?limit=' + str(body.get('data').get('options')[0]["value"])
        http = urllib3.PoolManager()
        r = http.request("GET" ,url, headers=headers)
        msgs = json.loads(r.data)
        for i in msgs:
          if len(i["attachments"]):
            bucket_name = 'discordattachments'
            key =  i["channel_id"] + '_' + i["id"] + '_' + i["attachments"][0]["id"] + '.' + i["attachments"][0]["url"].split('.')[-1]
            post_url = create_presigned_post(bucket_name, key)
            sns.publish(
                    TopicArn = "arn:aws:sns:us-east-2:673135797624:s3queue",
                    Message = json.dumps({
                    's3_key': key,
                    'attachment_url': i["attachments"][0]["url"],
                    'presigned_s3': post_url,
                    'timestamp': i["timestamp"],
                    'filename': i["attachments"][0]["filename"],
                    'author': i["author"]["username"]
                })
                )
            # lambda_client.invoke(
            #     FunctionName = os.environ["SyncHandlerARN"],
            #     InvocationType = 'Event',
            #     Payload = json.dumps({
            #         's3_key': key,
            #         'attachment_url': i["attachments"][0]["url"],
            #         'presigned_s3': post_url,
            #         'timestamp': i["timestamp"],
            #         'filename': i["attachments"][0]["filename"],
            #         'author': i["author"]["username"]
            #     })
            # )
    elif body.get('data').get('name') == 'search':
        lambda_client.invoke(
                FunctionName = os.environ["SearchHandler"],
                InvocationType = 'Event',
                Payload = json.dumps({
                    'query': body.get('data').get('options')[0]["value"],
                    'headers': headers,
                    'channel_id': body.get('channel_id')
                })
            )
        return {
            "type": RESPONSE_TYPES['MESSAGE_WITH_SOURCE'],
            "data": {
                "tts": False,
                "content": "Searching....",
                "embeds": [],
                "allowed_mentions": []
            }
        }
    
    return {
        "type": RESPONSE_TYPES['MESSAGE_WITH_SOURCE'],
        "data": {
            "tts": False,
            "content": "Files have been indexed and are now searchable.",
            "embeds": [],
            "allowed_mentions": []
        }
    }