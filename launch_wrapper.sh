#!/bin/bash

set -eu
set -o pipefail

stack_name='infratest'


# Cloudstrap precreate
echo "Creating cloudstrap bucket"
cloudstrap_bucket="cloudstrap.test-cloud.us-east-1.infra.leafme"
aws s3 mb s3://${cloudstrap_bucket}

# TODO this is not a good name going forward because we will want one for each
# region.
template_bucket='leafme-infra-cfn-templates'

echo "Creating S3 bucket for cloudformation template"
aws s3 mb s3://${template_bucket} --region us-east-1

echo "Generating template"
python generate.py -o ${stack_name}.template

echo "Uploading template to bucket"
aws s3 cp ${stack_name}.template s3://${template_bucket}/${stack_name}.template

echo "Setting template ACL"
aws s3api put-object-acl --bucket ${template_bucket} --key ${stack_name}.template --grant-read 'uri="http://acs.amazonaws.com/groups/global/AllUsers"'

# Zookeeper precreate
zookeeper_bucket="zookeeper.test-cloud.us-east-1.infra.leafme"
aws s3 cp bootstrap/primary s3://${zookeeper_bucket}/exhibitors/primary

# cloudformation stage - destroy the current stack if it exists
ret=0
aws cloudformation describe-stacks --stack-name ${stack_name} || ret=$?
if [[ $ret -eq 0 ]]; then
    echo "Deleting stack named ${stack_name}"
    aws cloudformation delete-stack --stack-name ${stack_name}
fi

# Now wait for the stack to die
while [[ 1 ]]; do
    ret=0
    stack_status=""
    json=$(aws cloudformation describe-stacks --stack-name ${stack_name}) || ret=$?
    if [[ ret -eq 255 ]]; then
        echo "Stack deleted. Continuing..."
        break
    fi

    # Determine if the stack is still being deleted
    stack_status=$(echo $json | jq '.Stacks[0].StackStatus')
    if [[ $stack_status == '"DELETE_IN_PROGRESS"' ]]; then
        echo "Stack still in state ${stack_status}. Waiting..."
    else
        echo "Stack in unexpected state ${stack_status}. Try running script again."
        exit 1
    fi
    sleep 30
done

# Recreate the stack
echo "Creating stack ${stack_name}"
aws cloudformation create-stack --stack-name ${stack_name} --template-url https://s3.amazonaws.com/${template_bucket}/${stack_name}.template --capabilities CAPABILITY_IAM --parameters ParameterKey=KeyName,ParameterValue=infra,UsePreviousValue=false --on-failure ROLLBACK

# Wait for stack creation
while [[ 1 ]]; do
    ret=0
    stack_status=""
    json=$(aws cloudformation describe-stacks --stack-name ${stack_name}) || ret=$?
    stack_status=$(echo $json | jq '.Stacks[0].StackStatus')
    if [[ $stack_status == '"CREATE_COMPLETE"' ]]; then
        # This is done, exit the loop
        echo "Stack created"
        break
    elif [[ $stack_status == '"CREATE_IN_PROGRESS"' ]]; then
        echo "Stack still in state ${stack_status}. Waiting"
        sleep 30
    else
        echo "Stack in unrecoverable state ${stack_status}. Try running this script again."
        exit 1
    fi
done

# Now the stack is created, so attempt to do more with it
