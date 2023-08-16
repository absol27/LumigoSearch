import json
import boto3
import urllib3
import time
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


def create_database(yb):
    try:
        with yb.cursor() as yb_cursor:
            yb_cursor.execute("DROP TABLE IF EXISTS files")
            yb_cursor.execute("DROP TABLE IF EXISTS keywords")
            yb_cursor.execute("DROP TABLE IF EXISTS file_keywords")
            create_table_stmt = """
                    CREATE TABLE files (
                    id SERIAL PRIMARY KEY,
                    channel_id VARCHAR(255) NOT NULL,
                    message_id VARCHAR(255),
                    attachment_id VARCHAR(255),
                    timestamp VARCHAR(255),
                    filename VARCHAR(255) NOT NULL,
                    author VARCHAR(255)
                );
                
                CREATE TABLE keywords (
                    id SERIAL PRIMARY KEY,
                    keyword VARCHAR(255) NOT NULL
                );
                
                CREATE TABLE file_keywords (
                    file_id INT REFERENCES files(id),
                    keyword_id INT REFERENCES keywords(id),
                    PRIMARY KEY (file_id, keyword_id)
                );
            """
            yb_cursor.execute(create_table_stmt)
        yb.commit()
    except Exception as e:
        print("Exception while creating tables")
        print(e)
        exit(1)

    print(">>>> Successfully created tables.")

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
    sqs = boto3.client('sqs')
    queue_url = 'https://sqs.us-east-2.amazonaws.com/673135797624/discordbot'

    try:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,  # Adjust as needed
            WaitTimeSeconds=20  # Adjust as needed
        )
    except Exception as e:
        print("Error:", str(e))
    # TODO implement
    message = json.loads(response["Messages"][0]["Body"])
    print(message)
    event1 = json.loads(message["Message"])
    http = urllib3.PoolManager()
    file = http.request("GET", event1['attachment_url'])
    post_url = event1["presigned_s3"]
    fields = post_url["fields"]  # Additional form fields
    fields["file"] = ("", file.data)
    # http_resp = http.requests("POST", post_url["url"], data = post_url["fields"], files = {'file': file.data})
    post_response = http.request(
    'POST',
    post_url["url"],
    fields = fields)
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
    
    print(">>>> Connecting to YugabyteDB!")

    try:
        if config['sslMode'] != '':
            yb = psycopg2.connect(host=config['host'], port=config['port'], database=config['dbName'],
                                  user=config['dbUser'], password=config['dbPassword'],
                                  sslmode=config['sslMode'], sslrootcert=config['sslRootCert'],
                                  connect_timeout=10)
        else:
            yb = psycopg2.connect(host=config['host'], port=config['port'], database=config['dbName'],
                                  user=config['dbUser'], password=config['dbPassword'],
                                  connect_timeout=10)
    except Exception as e:
        print("Exception while connecting to YugabyteDB")
        print(e)
        exit(1)

    print(">>>> Successfully connected to YugabyteDB!")
    # create_database(yb)
    with yb.cursor() as yb_cursor:
        curr_msg = event1["s3_key"].split('_')
        yb_cursor.execute("""
            INSERT INTO files (channel_id, message_id, attachment_id, timestamp, filename, author)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (
                curr_msg[0],
                curr_msg[1],
                curr_msg[2].split('.')[0],
                event1["timestamp"],
                event1["filename"],
                event1["author"]
        ))
        file_id = yb_cursor.fetchone()[0]
        for j in entities["Entities"]:
            if j['Score'] > 0.75:
                
                # for keyword in keywords:
                yb_cursor.execute("INSERT INTO keywords (keyword) VALUES (%s) RETURNING id", (j["Text"][0:250],))
                keyword_id = yb_cursor.fetchone()[0]  # Get the inserted keyword's ID
        
                # Associate keyword with the file
                yb_cursor.execute("INSERT INTO file_keywords (file_id, keyword_id) VALUES (%s, %s)", (file_id, keyword_id))
            
                yb.commit()
    yb.close()
    return {
        'statusCode': 200
    }