

## Usage
The Lambda uses boto3 to tag RDS Snapshots by propagating missing tags down from the parent RDS instance (once tagging is corrected).

This function only propagates-down tags which are defined as mandatory within your configuration of the managed AWS Config rule for required tagging, and will not overwrite any existing tags.  

If the parent RDS instance has been terminated, we are able to add placeholder tagging.  These tag values can be set in the Lambda environment variables for a given tag keyname with the variable name {keyname}_DefaultValue. If there is a '_DefaultValue' available for a given missing key for an orphaned RDS snapshot, then it is used.  If there is no enviornment variable we also have a CATCH_ALL_TAG_VALUE which is our fall-back tag value.


The logic works as follows:
 
1. Get all the non-compliant RDS snapshots by checking AWS Config compliance (taking the TAG_COMPLIANCE_RULE_NAME environment variable which is mandatory for the Lambda to run.)
2. Fetch the list of mandatory tags using AWS Config rule as the source of truth
3. Iterate through all the non-compliant snapshots
4. For each snapshot check if the parent instance is present
5. If parent is there, copy across any of the mandatory tags we already have, but don’t overwrite
6. If the parent is there and is missing a certain tag, we don’t add a placeholder
7. If the parent is missing, we go ahead and add placeholder tags

Placeholders are defined in the Lambda environment variables as {keyname}_DefaultValue (e.g. CostCentre_DefaultValue)
If we are tagging a snapshot with a deleted parent instance, we use the matching environment variable
If an environment variable does not exist for this particular tag, we use the CATCH_ALL_TAG_VALUE (which is mandatory for the lambda function to run).
Full logging is written to CloudWatch to show what was and was not tagged on a given run.
 
## Environment Variables
Example environment variables:
```
Application_DefaultValue: GeneralIT
CATCH_ALL_TAG_VALUE: Unknown
CostCentre_DefaultValue: BaseITCostCentre
Environment_DefaultValue: Development
ManagedBy_DefaultValue: support.team@mycompany.com
TAG_COMPLIANCE_RULE_NAME: required-tags
```

## Deployment
The Lambda Function should be deployed as a Python 3.6 function, with a CloudWatch event trigger (e.g. daily) and a 5 minute timeout.

There are two mandatory Environment Variables CATCH_ALL_TAG_VALUE and TAG_COMPLIANCE_RULE_NAME.
You may also add any {tagvalue}_DefaultValue for desired tag values where the parent instance no longer exists.
 

The IAM Role to run the function as requires the Managed Policy AWSLambdaBasicExecutionRole and the below additional policy:
``` 
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "ReadConfigAndApplyTags",
            "Effect": "Allow",
            "Action": [
                "rds:AddTagsToResource",
                "config:GetComplianceDetailsByConfigRule",
                "rds:ListTagsForResource",
                "rds:DescribeDBSnapshots",
                "rds:DescribeDBInstances",
                "config:DescribeConfigRules"
            ],
            "Resource": "*"
        }
    ]
}
```
## Sample
A sample log for a run of the function is below:

```
START RequestId: e9107ff4-1545-11e9-9e51-fb0a66188d7b Version: $LATEST
Starting RDS Snapshot Tagger....
==================================
Mandatory Tags for RDS Volumes (according to AWS Config rule) are currently: {'CostCentre', 'SecondMandatoryTag', 'Environment', 'ManagedBy'}
Checking AWS Config Compliance results.....
================================================
Found 4 RDS Snapshots which are missing one or more of these tags. Attempting to fix any non-compliant..
================================================
Beginning Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ...
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ...The parent RDS instance rds-development-mssql-singleaz exists, will copy down any missing tags
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Tag is missing on the snapshot: CostCentre
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Found an matching tag value for CostCentre on the attached parent RDS instance ( MyCostCentre ) so copying that to Snapshot...
trying to tag arn:aws:rds:ap-southeast-2:035112159662:snapshot:rds:rds-development-mssql-singleaz-2019-01-08-00-43 with tag: [{'Key': 'CostCentre', 'Value': 'MyCostCentre'}]
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Tag is missing on the snapshot: SecondMandatoryTag
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Tag is missing on the instance: SecondMandatoryTag - leaving the Snapshot tag blank. If the parent RDS instance is tagged we will fix the snapshot on the next run..
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Tag is missing on the snapshot: Environment
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-00-43 ..Found an matching tag value for Environment on the attached parent RDS instance ( Development ) so copying that to Snapshot...
trying to tag arn:aws:rds:ap-southeast-2:035112159662:snapshot:rds:rds-development-mssql-singleaz-2019-01-08-00-43 with tag: [{'Key': 'Environment', 'Value': 'Development'}]
 
Beginning Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-13-25 ...
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-13-25 ...The parent RDS instance rds-development-mssql-singleaz exists, will copy down any missing tags
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-13-25 ..Tag is missing on the snapshot: SecondMandatoryTag
Snapshot: rds:rds-development-mssql-singleaz-2019-01-08-13-25 ..Tag is missing on the instance: SecondMandatoryTag - leaving the Snapshot tag blank. If the parent RDS instance is tagged we will fix the snapshot on the next run..
 
Beginning Snapshot: rds:rds-development-mssql-singleaz-2019-01-09-13-25 ...
Snapshot: rds:rds-development-mssql-singleaz-2019-01-09-13-25 ...The parent RDS instance rds-development-mssql-singleaz exists, will copy down any missing tags
Snapshot: rds:rds-development-mssql-singleaz-2019-01-09-13-25 ..Tag is missing on the snapshot: ManagedBy
Snapshot: rds:rds-development-mssql-singleaz-2019-01-09-13-25 ..Found an matching tag value for ManagedBy on the attached parent RDS instance ( DBA ) so copying that to Snapshot...
trying to tag arn:aws:rds:ap-southeast-2:035112159662:snapshot:rds:rds-development-mssql-singleaz-2019-01-09-13-25 with tag: [{'Key': 'ManagedBy', 'Value': 'DBA'}]
 
Beginning Snapshot: snapshotofdeletedinstance ...
Snapshot: snapshotofdeletedinstance ...The parent RDS instance databasesforyou does not appear to exist. We will add placeholder tagging instead.
Snapshot: snapshotofdeletedinstance ..No Snapshot tag value found for CostCentre so applying placeholder tag
Snapshot: snapshotofdeletedinstance ..No Snapshot tag value found for SecondMandatoryTag so applying placeholder tag
Snapshot: snapshotofdeletedinstance ..No Snapshot tag value found for Environment so applying placeholder tag
END RequestId: e9107ff4-1545-11e9-9e51-fb0a66188d7b
```