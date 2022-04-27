import json
import boto3
import time
import requests

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    table = dynamodb.Table('DocSearch')

    get_key = table.scan(
        ProjectionExpression = "keyword"
    )
    query = event["query"].strip().lower()
    results = []
    for i in get_key["Items"]:
        if query in i["keyword"].strip().lower():
            info = table.get_item(
                Key={
                    "keyword": i["keyword"]
                }
            )
            results.append(info["Item"])
    all_occ = []
    # print(results)
    
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
    r = requests.post(url, headers = event["headers"], json = message_text)
    
    return {
        'statusCode': 200
        }
