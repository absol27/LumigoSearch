import json
import boto3
import time
import urllib3
import psycopg2
import psycopg2.extras

config = {
    'host': 'us-east-1.0fd7b714-461d-47fb-9b73-660e507d3bb0.aws.ybdb.io',
    'port': '5433',
    'dbName': 'yugabyte',
    'dbUser': 'admin',
    'dbPassword': 'epRTlf168sjCaXzzDQg9FrmUhkvBGe',
    'sslMode': '',
    'sslRootCert': ''
}

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    query = event["query"].strip().lower()

    connection = psycopg2.connect(
        config
    )
    cursor = connection.cursor()

    query_sql = """
    SELECT f.* FROM files f
    JOIN file_keywords fk ON f.id = fk.file_id
    JOIN keywords k ON fk.keyword_id = k.id
    WHERE k.keyword = %s
    """
    cursor.execute(query_sql, (query,))
    results = cursor.fetchall()

    connection.close()
    all_occ = []
    for i in results:
      for j in i["files"]:
        x = {
          'filename': j["filename"],
          'author':j["author"],
          'timestamp': j["timestamp"].split('T')[0],
          'attachmentlink':'https://cdn.discordapp.com/attachments/'+j["channelid"]+'/' + j["attachmentid"] +'/' + j["filename"],
          'linktomessage': 'https://discordapp.com/channels/879399976512421900/'+j["channelid"]+'/'+j["messageid"]
        }
        all_occ.append(x)

    fields = []
    
    for x in all_occ:
      fields.extend([
        {
          "name": 'Author',
          "value": x["author"],
          "inline": True
        },
        {
          "name": "Filename",
          "value": x["filename"],
          "inline": True
        },
        {
          "name": "Timestamp",
          "value": x["timestamp"],
          "inline": True
        },
        {
          "name": "Message",
          "value": "[Go to Message]("+x["linktomessage"]+')',
          "inline": True
        },
        {
          "name": "Attachment URL",
          "value": "[Download Attachment]("+x["attachmentlink"]+')',
          "inline": True
        },
        {
            "name": chr(173),
            "value": chr(173)
        }
      ])
    
    url = 'https://discord.com/api/v8/channels/' + event['channel_id'] + '/messages'
    message_text = {
        "tts": False,
        "content": "",
        "embeds": [
                {
                  "type": "rich",
                  "title": 'Seach Results',
                  "description": 'Query results',
                  "color": 0x2bff00,
                  "fields": fields
                }
            ]
        }
    http = urllib3.PoolManager()
    r = http.requests("POST",url, headers = event["headers"], json = message_text)
    
    return {
        'statusCode': 200
        }
