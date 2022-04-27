import json
import boto3
import requests
import time

textract = boto3.client('textract')
comprehend = boto3.client('comprehend')
dynamodb = boto3.resource('dynamodb')

def InvokeTextDetectJob(s3BucketName, objectName):
    response = None
    client = boto3.client('textract')
    response = client.start_document_text_detection(
            DocumentLocation={
                      'S3Object': {
                                    'Bucket': s3BucketName,
                                    'Name': objectName
                                }
           })
    return response["JobId"]

def CheckJobComplete(jobId):
    time.sleep(5)
    client = boto3.client('textract')
    response = client.get_document_text_detection(JobId=jobId)
    status = response["JobStatus"]
    print("Job status: {}".format(status))
    while(status == "IN_PROGRESS"):
        time.sleep(5)
        response = client.get_document_text_detection(JobId=jobId)
        status = response["JobStatus"]
        print("Job status: {}".format(status))
    return status

def JobResults(jobId):
    pages = []
    client = boto3.client('textract')
    response = client.get_document_text_detection(JobId=jobId)
 
    pages.append(response)
    print("Resultset page recieved: {}".format(len(pages)))
    nextToken = None
    if('NextToken' in response):
        nextToken = response['NextToken']
        while(nextToken):
            response = client.get_document_text_detection(JobId=jobId, NextToken=nextToken)
            pages.append(response)
            print("Resultset page recieved: {}".format(len(pages)))
            nextToken = None
            if('NextToken' in response):
                nextToken = response['NextToken']
    return pages



def lambda_handler(event, context):
    # TODO implement
    event1 = json.loads(event["Records"][0]["body"])
    file = requests.get(event1['attachment_url'])
    post_url = event1["presigned_s3"]
    http_resp = requests.post(post_url["url"], data = post_url["fields"], files = {'file': file.content})
    
    # Function invokes
    jobId = InvokeTextDetectJob('discordattachments', event1["s3_key"])#'879399976512421903_968163281585979402_968163281393025085.pdf')
    print("Started job with id: {}".format(jobId))
    pdf_text = ""
    if(CheckJobComplete(jobId)):
        response = JobResults(jobId)
        for resultPage in response:
            for item in resultPage["Blocks"]:
                if item["BlockType"] == "LINE":
                    pdf_text += item["Text"]
    # print (pdf_text)
    entities = comprehend.detect_entities(
        Text = pdf_text,
        LanguageCode = 'en'
    )
    for j in entities["Entities"]:
        if j['Score'] > 0.75:
            table = dynamodb.Table('DocSearch')
            curr_msg = event1["s3_key"].split('_')
            get_key = table.get_item(
                Key={
                    "keyword": j["Text"]
                }
            )
            newentry = {
                'channelid': curr_msg[0],
                'messageid': curr_msg[1],
                'attachmentid': curr_msg[2].split('.')[0],
                'timestamp': event1["timestamp"],
                'filename': event1["filename"],
                'author': event1["author"]
            }
            if "Item" in get_key:
                response = table.update_item(
                        Key={
                            "keyword": j["Text"]
                        },
                        UpdateExpression="set files=list_append(files, :newfile)",
                        ExpressionAttributeValues={ 
                            ':newfile': [newentry]
                    
                        },
                        ReturnValues="UPDATED_NEW"
                    )
            else:
                response = table.put_item(
                        Item = {
                            'keyword': j["Text"],
                            'files':[newentry]
                        }
                    )
            print(j['Text'])
    return {
        'statusCode': 200
    }
