#!/usr/bin/env python

"""
A simple script that reads in a CSV file, parses out the EC2 instance
IDs from the first column, checks AWS SSM to make sure it's a managed
node with the agent running, then uses AWS SSM Run Command to uninstall
a specified package that was installed by AWS SSM Distributor.

Usage: python uninstall.py -p <my distributor package> <path to csv>
"""

import argparse
import csv
import logging
import sys
from typing import List
import boto3
from botocore.exceptions import ClientError

# Configuration
REGION_NAME = 'us-east-1'
ssm = boto3.client('ssm', region_name=REGION_NAME)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='uninstall.log'
)

# Arguments
parser = argparse.ArgumentParser(
    description=('Uninstalls a package from EC2 instances that was previously '
                 'installed with AWS Systems Manager Distributor')
)
parser.add_argument(
    'resource_id_file', help='The name of the CSV file containing the resource IDs')
parser.add_argument(
    '-p', '--package-name', help='The name of the package to uninstall', required=True)
parser.add_argument(
    '-m', '--mode', choices=['distributor', 'powershell'],
    default='distributor',
    help='Operating mode (default: distributor)'
)
args = parser.parse_args()

if args.resource_id_file is None or args.package_name is None:
    parser.print_help()
    sys.exit(1)

RESOURCE_ID_FILE = args.resource_id_file
PACKAGE_NAME = args.package_name
MODE = args.mode


def uninstall_package(items: List[str], batch_size: int = 50) -> None:
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


def process_batch(batch: List[str]) -> None:
    """
    Runs the `AWS-ConfigureAWSPackage` AWS SSM Run Document against a batch of up to
    50 valid EC2 instance IDs

    Args:
        batch: List of valid EC2 instance IDs
    """

    try:
        logging.info('Uninstalling %s using %s from instance IDs: %s',
                     PACKAGE_NAME, MODE, str(batch))
        if MODE == 'distributor':
            response = ssm.send_command(
                InstanceIds=batch,
                DocumentName='AWS-ConfigureAWSPackage',
                Parameters={
                    'action': ['Uninstall'],
                    'name': [PACKAGE_NAME]
                },
                CloudWatchOutputConfig={
                    'CloudWatchOutputEnabled': True,
                    'CloudWatchLogGroupName': f"/tm/{PACKAGE_NAME.lower().replace(' ', '-')}Uninstall"
                }
            )
        else:
            response = ssm.send_command(
                InstanceIds=batch,
                DocumentName='AWS-RunPowerShellScript',
                Parameters={
                    'commands': [
                        "$agentInstalled = Get-WmiObject -Class Win32_Product | Where-Object {$_.Name -eq \"Rapid7 Insight Agent\"}",
                        "if ($agentInstalled) {",
                        "    $uninstallResult = msiexec.exe /x $($agentInstalled.IdentifyingNumber) /qn",
                        "    if ($LASTEXITCODE -ne 0) {",
                        "        Write-Output \"Failed to uninstall Rapid7 Insight Agent. Exit code: $LASTEXITCODE\"",
                        "    }",
                        "} else {",
                        "    Write-Output \"Rapid7 Insight Agent is not installed.\"",
                        "}"
                    ]
                },
                CloudWatchOutputConfig={
                    'CloudWatchOutputEnabled': True,
                    'CloudWatchLogGroupName': f"/tm/{PACKAGE_NAME.lower().replace(' ', '-')}Uninstall"
                }
            )
        command_id = response.get('Command', {}).get('CommandId', '--')
        status = response.get('Command', {}).get('Status', '--')
        logging.info('Command ID: %s Status: %s', command_id, status)
    except ClientError as e:
        logging.error('Error processing batch: %s', str(e))
        sys.exit(1)


def check_instances(instance_ids: List[str]) -> List[str]:
    """
    Checks the SSM agent status for each EC2 instance ID that is passed. If the ID
    is invalid it is ignored. Otherwise, it will get the "PingStatus" of the agent.

    Args:
        instance_ids: A list of EC2 instance IDs to check
    Returns:
        valid_ids: A list of EC2 instance IDs that exist and the SSM agent is online
    """

    logging.info('Checking %s instance ID(s)', str(instance_ids))
    valid_ids = []
    for i in range(0, len(instance_ids), 100):
        batch = instance_ids[i:i + 100]
        next_token = None
        while True:
            try:
                if next_token:
                    response = ssm.describe_instance_information(
                        Filters=[{'Key': 'InstanceIds',
                                  'Values': batch}],
                        NextToken=next_token
                    )
                else:
                    response = ssm.describe_instance_information(
                        Filters=[
                            {'Key': 'InstanceIds', 'Values': batch}]
                    )
                for instance in response['InstanceInformationList']:
                    if instance['PingStatus'] == 'Online':
                        logging.info(
                            'Valid instance found with ID %s', instance['InstanceId'])
                        valid_ids.append(instance['InstanceId'])
                    else:
                        logging.warning(
                            'Valid instance %s is not online', instance['InstanceId'])

                if 'NextToken' in response:
                    next_token = response['NextToken']
                else:
                    break

            except ClientError as e:
                logging.error('Error processing instance: %s', str(e))
                sys.exit(1)

    logging.info('Found %d valid ID(s) out of %d',
                 len(valid_ids), len(instance_ids))
    return valid_ids


if __name__ == '__main__':
    # Read the CSV file
    with open(RESOURCE_ID_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # Skip header
        unique_resource_ids = {row[0] for row in reader if row}

    # Check if instances are valid
    # A valid instance is one in which the instance ID exists and the instance is running
    valid_instances = check_instances(list(unique_resource_ids))

    # Exit if no instances found
    if not valid_instances:
        logging.warning('No valid instances found')
        sys.exit(1)

    uninstall_package(valid_instances)
