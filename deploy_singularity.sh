#!/bin/bash

# terminate all subprocessed spawned off this one when killed with ctrl-c
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

set -ue

# find the VPN server
find_vpn_server() {
    # use the aws cli to find our active VPN server
    local ret=0
    local json=$(aws --region us-east-1 ec2 describe-instances --filters "Name=tag:Deploy,Values=vpn" "Name=instance-state-name,Values=running") || ret=$?

    local public_dns=$(echo $json | jq '.Reservations[0].Instances[0].PublicDnsName' --raw-output)
    if [[ $public_dns == "null" ]]; then
        echo "No VPN instances found yet"
        return "null"
    fi

    echo $public_dns
}

# determine the VPN server to use and then substitute our template and connect to it
vpn_server="null"
while [[ 1 ]]; do
    vpn_server=$(find_vpn_server)
    if [[ ${vpn_server} == "null" ]]; then
        echo "VPN server not available yet, waiting..."
        sleep 30
    else
        echo "Found vpn server with address ${vpn_server}"
        break
    fi
done

vpn_config_dir="wlee-infra-vpn.tblk"
cat ${vpn_config_dir}/config.ovpn.j2 | sed -e "s/\${vpnhost}/${vpn_server}/" > ${vpn_config_dir}/config.ovpn

# start the VPN process in the background
pushd ${vpn_config_dir}
sudo /usr/local/sbin/openvpn --config config.ovpn --daemon
#vpn_pid=$(pgrep P $$ openvpn)
popd

#echo "${vpn_pid} is up"

# We're just going to be optimistic and assume the VPN will connect (but we'll limit ourselves)

# Get the list of mesos_master instances from EC2
sleep 20
mesos_master_ip="null"
while [[ 1 ]]; do
    ret=0
    json=$(aws --region us-east-1 ec2 describe-instances --filters "Name=tag:Deploy,Values=mesos_master" "Name=instance-state-name,Values=running") || ret=$?  mesos_master_ip=$(echo $json | jq '.Reservations[0].Instances[0].PrivateIpAddress' --raw-output)
    mesos_master_ip=$(echo $json | jq '.Reservations[0].Instances[0].PrivateIpAddress' --raw-output)
    if [[ $mesos_master_ip == "null" ]]; then
        echo "No Mesos master instances found yet, waiting and retrying"
        sleep 30
    else
        echo "Found a Mesos master at ${mesos_master_ip}. Attempting to connect and deploy"
        break
    fi
done

# Retrieve the master via Marathon
# TODO the way we start our masters, we expect this to come back as something like ip-OCTET-OCTET-OCTET-OCTET:PORT
leader_server=$(curl http://${mesos_master_ip}:8080/v2/leader | jq '.leader' --raw-output | cut -d'-' -f2-5 | sed 's/-/./g')
echo "The current leader server is ${leader_server}"

# Now hit the leader Marathon with a request to deploy Singularity
# Download the Singularity Shaded jar
singularity_jar_name="SingularityService-0.4.1-shaded.jar"
singularity_jar_url="https://repo1.maven.org/maven2/com/hubspot/SingularityService/0.4.1/SingularityService-0.4.1-shaded.jar"
curl ${singularity_jar_url} -o ${singularity_jar_name}

singularity_bundle="SingularityService-latest.tgz"
mkdir singularityservice || true
cp $singularity_jar_name singularityservice
cp singularity_config.yml singularityservice
tar cvzf $singularity_bundle singularityservice
# Upload it to a bucket
marathon_deploy_bucket="leafme-infra-marathon-deploy-bucket"
aws s3 mb s3://${marathon_deploy_bucket} --region us-east-1
# Upload the file

echo "Uploading $singularity_bundle"
aws s3 cp $singularity_bundle s3://${marathon_deploy_bucket}/$singularity_bundle
aws s3api put-object-acl --bucket ${marathon_deploy_bucket} --key $singularity_bundle --grant-read 'uri="http://acs.amazonaws.com/groups/global/AllUsers"'

# Cleaning up the folder
rm -rf singularityservice

# Now try to deploy it
echo "Deploying Singularity to Marathon"
curl -X POST -H "Accept: application/json" -H "Content-Type: application/json" http://${leader_server}/v2/apps -d @singularity.json

# TODO hacky cleanup of our VPN connection
echo "Done"
#echo "Terminating background OpenVPN connection with PID ${vpn_pid}"
#sudo kill $vpn_pid
