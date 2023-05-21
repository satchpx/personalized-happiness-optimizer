import os
import json
import boto3
import pprint 
import datetime
import urllib.parse
import pandas as pd

pp = pprint.PrettyPrinter(indent=4, compact=True)

def flatten_and_normalize(rekog_data):
    """
    Convert a Rekogntion JSON Blob into a Pandas Dataframe.
    The resulting dataframe is also normalized to be more suitable for AI/ML algorithms.
   
    It also appends estimated happiness and a random hour of the day (24 hour format)
    """
    stat_cols = [
                 'AgeLow', 'AgeHigh',
                 'Smile_T', 'Smile_F',
                 'Eyeglasses_T', 'Eyeglasses_F',
                 'Sunglasses_T', 'Sunglasses_F',
                 'Gender_Male', 'Gender_Female',
                 'Beard_T', 'Beard_F',
                 'Mustache_T', 'Mustache_F',
                 'Eyes_Open',  'Eyes_Closed',
                 'Mouth_Open', 'Mouth_Closed'
                ]
    stat_row = [
        rekog_data['AgeRange']['Low'],
        rekog_data['AgeRange']['High'],
        ( rekog_data['Smile']['Confidence']/100 if rekog_data['Smile']['Value'] else 0),
        ( rekog_data['Smile']['Confidence']/100 if not rekog_data['Smile']['Value'] else 0),
        ( rekog_data['Eyeglasses']['Confidence']/100 if rekog_data['Eyeglasses']['Value'] else 0),
        ( rekog_data['Eyeglasses']['Confidence']/100 if not rekog_data['Eyeglasses']['Value'] else 0),
        ( rekog_data['Sunglasses']['Confidence']/100 if rekog_data['Sunglasses']['Value'] else 0),
        ( rekog_data['Sunglasses']['Confidence']/100 if not rekog_data['Sunglasses']['Value'] else 0),
        ( rekog_data['Gender']['Confidence']/100 if rekog_data['Gender']['Value'] == 'Male' else 0),
        ( rekog_data['Gender']['Confidence']/100 if rekog_data['Gender']['Value'] == 'Female' else 0),
        ( rekog_data['Beard']['Confidence']/100  if rekog_data['Beard']['Value'] else 0),
        ( rekog_data['Beard']['Confidence']/100 if not rekog_data['Beard']['Value'] else 0),
        ( rekog_data['Mustache']['Confidence']/100 if rekog_data['Mustache']['Value'] else 0),
        ( rekog_data['Mustache']['Confidence']/100 if not rekog_data['Mustache']['Value'] else 0),
        ( rekog_data['EyesOpen']['Confidence']/100 if rekog_data['EyesOpen']['Value'] else 0),
        ( rekog_data['EyesOpen']['Confidence']/100 if not rekog_data['EyesOpen']['Value'] else 0),
        ( rekog_data['MouthOpen']['Confidence']/100 if rekog_data['MouthOpen']['Value'] else 0),
        ( rekog_data['MouthOpen']['Confidence']/100 if not rekog_data['MouthOpen']['Value'] else 0),
    ]
   
    emotion_row = [ y['Confidence']/100 for y in rekog_data['Emotions'] ]
    emotion_cols = [ y['Type'] for y in rekog_data['Emotions'] ]
    row = stat_row + emotion_row
    cols = stat_cols + emotion_cols
    return pd.DataFrame([row],columns=cols)

def estimate_happiness(df):
    """Given a pandas array of flattened Rekog data, return the estimated happiness of each"""
    return df['HAPPY']
    
def flatten_and_normalize2(rekog_data):
    df = flatten_and_normalize(rekog_data)
    h_est = estimate_happiness(df)
    hour = datetime.datetime.now().hour
    df.insert(0,'h_est', h_est)
    df.insert(0,'HOUR', hour)
    return df
 

def lambda_handler(event, context):

    s3 = boto3.client('s3')
    # model_arn='model arn'
    client=boto3.client('rekognition')
    ddb = boto3.client('dynamodb')
    
    ENDPOINT_NAME = os.environ['ENDPOINT_NAME']
    sm = boto3.client('runtime.sagemaker')

    # Get the object from the event
    print(event)
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    ### debug
    # bucket="pho-training-data-usw2"
    # key="29023Exp3distressed_actor_307.jpg"
    ###
    
    # object_response = s3.get_object(Bucket=bucket, Key=key)
    tag_response = s3.get_object_tagging(Bucket=bucket, Key=key)
    object_tags = tag_response['TagSet']
    sessionId = None
    sequenceId = None

    for tag in object_tags:
        if tag['Key'] == 'sessionId':
            sessionId = tag['Value']
        if tag['Key'] == 'sequenceId':
            sequenceId = tag['Value']

    if sessionId is None or sequenceId is None:
        print("[ERROR]: Session ID/ SequenceId not set!")
        return
    
    #process S3 image object
    response = client.detect_faces(
	    Image={
			"S3Object": {
				"Bucket": bucket,
				"Name": key,
			}
		},
	    Attributes=['ALL'],
	)
    
    ddb_entry = {}
    resp_string = json.dumps(response)
    details = response['FaceDetails']
    
    # Build DF for Sagemaker 
    sm_df = flatten_and_normalize2(details[0])
    
    ddb_entry['session_id'] = {'S': sessionId}
    dateTimeObj = datetime.datetime.now()
    timestamp = dateTimeObj.strftime("%d-%b-%Y (%H:%M:%S.%f)")
    ddb_entry['timestamp'] = {'S': timestamp}
    if sequenceId == 'pre':
        ddb_entry['pre_response'] = {'S': resp_string}
    elif sequenceId == 'post':
        ddb_entry['post_response'] = {'S': resp_string}

    resp = ddb.put_item(TableName='pho-test', Item=ddb_entry)

    if sequenceId == 'post':
        #compute/ compare happiness levels
        # item = ddb.get
        print("foo")

    # Call Sagemaker
    sm_response = sm.invoke_endpoint(EndpointName=ENDPOINT_NAME,
                                     Body=payload)
                                    
    print(sm_response)

    ### DEBUG
    # for face in details:
    #     print ("Face ({Confidence}%)".format(**face))
    # # emotions
    # for emotion in face['Emotions']:
    #     print ("  {Type} : {Confidence}%".format(**emotion))
    # # quality
    # for quality, value in face['Quality'].iteritems():
    #     print ("  {quality} : {value}".format(quality=quality, value=value))
    # # facial features
    # for feature, data in face.iteritems():
    #     print ("  {feature}({data[Value]}) : {data[Confidence]}%".format(feature=feature, data=data))
    ### END_DEBUG
