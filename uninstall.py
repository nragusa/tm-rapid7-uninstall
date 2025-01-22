#!/usr/bin/env python

import csv
import logging
import sys
import boto3
from botocore.exceptions import ClientError

RESOURCE_ID_FILE = 'resource_id.csv'
AGENT_NAME = 'wget'
REGION_NAME = 'us-east-2'


# Basic setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='uninstall.log'
)


def uninstall_package(items, batch_size=50):
    """
    Process items in batches of specified size.

    Args:
        items: List of items to process
        batch_size: Maximum number of items per batch (default 50)
    """
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        # Process your batch here
        process_batch(batch)


def process_batch(batch):
    """
    Runs the `AWS-ConfigureAWSPackage` AWS SSM Run Document against a batch of up to
    50 valid EC2 instance IDs
    """
    client = boto3.client('ssm', region_name=REGION_NAME)
    try:
        client.send_command(
            InstanceIds=batch,
            DocumentName='AWS-ConfigureAWSPackage',
            Parameters={
                'action': ['Uninstall'],
                'name': [AGENT_NAME]
            },
            CloudWatchOutputConfig={
                'CloudWatchOutputEnabled': True,
                'CloudWatchLogGroupName': 'aws/ssm/Rapid7AgentUninstall'
            }
        )
    except ClientError as e:
        print(e)
        sys.exit(1)


def check_instances(instance_ids):
    ec2 = boto3.client('ec2', region_name=REGION_NAME)
    valid_ids = []

    # First try batch request
    for i in range(0, len(instance_ids), 100):
        batch = instance_ids[i:i + 100]
        try:
            response = ec2.describe_instances(InstanceIds=batch)
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] == 'running':
                        logging.info(
                            'Valid instance found with ID %s', instance['InstanceId'])
                        valid_ids.append(instance['InstanceId'])
                    else:
                        logging.warning(
                            'Valid instance %s is not running', instance['InstanceId'])
        except ClientError:
            # If batch fails, check instances individually
            for instance_id in batch:
                try:
                    response = ec2.describe_instances(
                        InstanceIds=[instance_id])
                    instance = response['Reservations'][0]['Instances'][0]
                    if instance['State']['Name'] == 'running':
                        logging.info(
                            'Valid instance found with ID %s', instance['InstanceId'])
                        valid_ids.append(instance['InstanceId'])
                    else:
                        logging.warning(
                            'Valid instance %s is not running', instance['InstanceId'])
                except ClientError:
                    logging.error(
                        'Instance %s is not valid', instance_id)

    return valid_ids


with open(RESOURCE_ID_FILE, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader, None)
    resource_id_list = [row for row in reader]

# Check if instances are valid
# A valid instance is one in which the instance ID exists and the instance is running
valid_instances = check_instances([item[0] for item in resource_id_list])

# Uninstall package from valid instances
uninstall_package(valid_instances)
