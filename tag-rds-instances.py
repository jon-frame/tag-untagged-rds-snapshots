import json
import boto3
import botocore
import os
import sys
import traceback

def get_required_tags(rulename):
    client = boto3.client('config')
    rules_details=client.describe_config_rules(
    ConfigRuleNames=rulename
    )
    #required tags
    required_tags=rules_details['ConfigRules'][0]['InputParameters']
    tags_as_json=json.loads(required_tags)
    items=tags_as_json.items()
    #print(items)
    #the tag config can include tag names and tag values
    #we only want to know required keynames as these are the names of required tags
    returned_tag_names = {v for (k,v) in items if 'Key' in k}
    print("Mandatory Tags for RDS Volumes (according to AWS Config rule) are currently: ",returned_tag_names)
    return returned_tag_names

def get_placeholder_tag_value(keyname):
    try: 
        env_var_name=keyname+"_DefaultValue"
        placeholder_value = os.environ[env_var_name]
        return placeholder_value
    except Exception as e:
        #print ("Could not find a default value for ",keyname," so using the catch-all tag value ",os.environ['CATCH_ALL_TAG_VALUE'])
        return os.environ['CATCH_ALL_TAG_VALUE']


def do_placeholder_tagging(snapshot_id, rds_snapshot_arn, tags_to_apply):
    #we check environment variables here for any default values to apply for given tags
    #where we can't find a matching enviornment variable we apply a catch-all placeholder tag
    rds_client = boto3.client('rds')
    rds_snapshot_tags = (rds_client.list_tags_for_resource(ResourceName=rds_snapshot_arn))['TagList']
    for tag in tags_to_apply:
        try:
            matching_snapshot_tag = [d for d in rds_snapshot_tags if d['Key'] == tag]
        except Exception as e:
            print ("Snapshot: ",snapshot_id,"..Error getting tags for Snapshot, there may be no tags at all")
            snapshot_tags=[]
            matching_snapshot_tag=[]
        if (len(matching_snapshot_tag))>0:
            #There is already a tag value for this key
            continue
        if (len(matching_snapshot_tag)==0):
            print("Snapshot: ",snapshot_id,"..No Snapshot tag value found for ",tag," so applying placeholder tag..")
            try:
                new_tag_value=get_placeholder_tag_value(tag)
                new_tag={"Key":tag,'Value':new_tag_value}
                rds_snapshot_tags.append(new_tag)
                #print ("Snapshot: ",snapshot_id,'..new tags: ',rds_snapshot_tags)
                rds_client.add_tags_to_resource(ResourceName=rds_snapshot_arn, Tags=[new_tag])
            except Exception as e:
                print("Snapshot: ",snapshot_id,'.exception..')
                print (e)
                traceback.print_exc()
    return

def do_tagging_propagation(snapshot_id, rds_snapshot_arn, parent_rds_instance_arn, tags_to_apply):
    rds_client = boto3.client('rds')
    rds_snapshot_tags = (rds_client.list_tags_for_resource(ResourceName=rds_snapshot_arn))['TagList']
    rds_instance_tags = (rds_client.list_tags_for_resource(ResourceName=parent_rds_instance_arn))['TagList']
    for tag in tags_to_apply:
        try:
            matching_snapshot_tag = [d for d in rds_snapshot_tags if d['Key'] == tag]
        except Exception as e:
            print ("Snapshot: ",snapshot_id,"..Error getting tags for Snapshot, there may be no tags at all")
            snapshot_tags=[]
            matching_snapshot_tag=[]
        if (len(matching_snapshot_tag))>0:
            #There is already a tag value for this key
            continue
        if (len(matching_snapshot_tag)==0):
            print("Snapshot: ",snapshot_id,"..Tag is missing on the snapshot: ",tag)
            try:
                matching_parent_rds_tag = [d for d in rds_instance_tags if d['Key'] == tag]
            except Exception as e:
                print("Snapshot: ",snapshot_id,"..Error getting tags for RDS instance, there may be no tags at all..")
                matching_parent_rds_tag=[]
            if (len(matching_parent_rds_tag))>0:
                print("Snapshot: ",snapshot_id,"..Found an matching tag value for ",tag," on the attached parent RDS instance (",matching_parent_rds_tag[0]['Value'],") so copying that to Snapshot...")
                #new_tags=rds_snapshot_tags+matching_parent_rds_tag
                print("trying to tag ",rds_snapshot_arn," with tag: ",matching_parent_rds_tag)
                try:
                    rds_client.add_tags_to_resource(ResourceName=rds_snapshot_arn, Tags=matching_parent_rds_tag)
                except Exception as e:
                    print ("Snapshot: ",snapshot_id,"..There was an error applying the tags: ",e)
            if (len(matching_parent_rds_tag)==0):
                print("Snapshot: ",snapshot_id,"..Tag is missing on the instance: ", tag,"  - leaving the Snapshot tag blank. If the parent RDS instance is tagged we will fix the snapshot on the next run..")
            
    print("")
    return


def lambda_handler(event, context):
    try:
        config_rule_name = os.environ['TAG_COMPLIANCE_RULE_NAME']
    except Exception as e:
        print("ERROR: Unable to determine the name of the config rule for tag compliance.. check Lambda Environment Variables for TAG_COMPLIANCE_RULE_NAME")
        sys.exit(1)
    try:
        catch_all_tag_value = os.environ['CATCH_ALL_TAG_VALUE']
    except Exception as e:
        print("ERROR: Unable to retrieve the CATCH_ALL_TAG_VALUE for snapshots with a deleted parent.. check Lambda Environment Variables")
        sys.exit(1)
    #boto3.set_stream_logger('')
    print('Starting RDS Snapshot Tagger....')
    print('==================================')
    rds_client=boto3.client('rds')
    #customise retry count for aws config client as we keep hitting throttling retry limit with default of 4..
    boto3_config=botocore.config.Config(retries={'max_attempts':10})
    client = boto3.client('config', config=boto3_config)
    paginator = client.get_paginator('get_compliance_details_by_config_rule')
    page_iterator = paginator.paginate(
        ConfigRuleName=config_rule_name,
        ComplianceTypes=['NON_COMPLIANT']
        )
    #get the tag names that the rule checks for
    required_tags=get_required_tags([config_rule_name])
    all_results=[]
    for page in page_iterator:
        results=page['EvaluationResults']
        all_results += results
    #filter all_results to just get rds snapshots
    non_compliant_snapshots= [x['EvaluationResultIdentifier']['EvaluationResultQualifier']['ResourceId'] for x in all_results if x['EvaluationResultIdentifier']['EvaluationResultQualifier']['ResourceType'] == 'AWS::RDS::DBSnapshot']
    print('Checking AWS Config Compliance results.....')
    print('================================================')
    print("Found ",len(non_compliant_snapshots)," RDS Snapshots which are missing one or more of these tags. Attempting to fix any non-compliant..")
    print('================================================')
    #print('List of snapshots to check: ',non_compliant_snapshots)
    for rds_snapshot in non_compliant_snapshots:
        #describe the snapshot to get the parent rds instance id
        #check if the parent rds instance exists
        #if it does call the tag fix function
        #but only for missing tags 
        snapshot_id=rds_snapshot
        print("Beginning Snapshot: ",snapshot_id,"...")
        snapshot_details=rds_client.describe_db_snapshots(DBSnapshotIdentifier=snapshot_id)
        rds_snapshot_arn = snapshot_details['DBSnapshots'][0]['DBSnapshotArn']
        parent_rds_instance_id = snapshot_details['DBSnapshots'][0]['DBInstanceIdentifier']
        try:
            parent_instance=rds_client.describe_db_instances(DBInstanceIdentifier=parent_rds_instance_id)
            print("Snapshot: ",snapshot_id,'...The parent RDS instance ',parent_rds_instance_id,' exists, will copy down any missing tags')
            parent_instance_arn=parent_instance['DBInstances'][0]['DBInstanceArn']
            #We copy down any missing tags which exist on parent. We don't add placeholders.
            #Expectation is that the RDS Instance non-compliance needs to be fixed by the team
            #This Lambda function will then fix up historical non-compliance on snapshots
            do_tagging_propagation(snapshot_id, rds_snapshot_arn, parent_instance_arn, required_tags)
        except Exception as e:
            print("Snapshot: ",snapshot_id,'...The parent RDS instance ',parent_rds_instance_id,' does not appear to exist. We will add placeholder tagging instead.')
            do_placeholder_tagging(snapshot_id, rds_snapshot_arn, required_tags) 
    return {
        'statusCode': 200,
        'body': json.dumps('RDS Snapshot Tag Check Completed succesfully..')
    }
