#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This module creates the jenkins instance and services

import json

from troposphere import Parameter, Ref, FindInMap, Base64, GetAtt, Tags
import troposphere.autoscaling as autoscaling
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE, EC2_INSTANCE_LAUNCH, EC2_INSTANCE_LAUNCH_ERROR, EC2_INSTANCE_TERMINATE_ERROR
import troposphere.cloudwatch as cloudwatch
import troposphere.ec2 as ec2
import troposphere.sns as sns
import troposphere.sqs as sqs
import troposphere.iam as iam

import config as cfn
from config import CIDR_PREFIX, VPC_NAME, CLOUDNAME, CLOUDENV, ASSUME_ROLE_POLICY, template
from config import USE_PRIVATE_SUBNETS, DEFAULT_ROUTE

def emit_configuration():
    # Parameters here
    jenkins_instance_class = template.add_parameter(
        Parameter(
            'JenkinsInstanceType', Type='String', Default='t2.micro',
            Description='Chef jenkins instance type',
            AllowedValues=cfn.usable_instances(),
            ConstraintDescription='Instance size must be a valid instance type'
        )
    )

    # jenkins IAM role
    jenkins_role_name = '.'.join(['jenkins', CLOUDNAME, CLOUDENV])
    jenkins_iam_role = template.add_resource(
        iam.Role(
            'JenkinsIamRole',
            AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
            Path="/",
            Policies=[
                iam.Policy(
                    PolicyName='JenkinsPolicy',
                    PolicyDocument=json.loads(cfn.load_template("jenkins_policy.json.j2",
                        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
                    ))
                ),
                iam.Policy(
                    PolicyName='JenkinsDefaultPolicy',
                    PolicyDocument=json.loads(cfn.load_template("default_policy.json.j2",
                        {"env": CLOUDENV, "cloud": CLOUDNAME, "region": "us-east-1"}
                    ))
                )
            ],
            DependsOn=cfn.vpcs[0].title
        )
    )

    jenkins_instance_profile = template.add_resource(
        iam.InstanceProfile(
            "JenkinsInstanceProfile",
            Path="/",
            Roles=[Ref(jenkins_iam_role)],
            DependsOn=jenkins_iam_role.title
        )
    )

    jenkins_user_data = cfn.load_template("default-init.bash.j2",
            {"env": CLOUDENV, "cloud": CLOUDNAME, "deploy": "jenkins"}
    )

    ingress_rules = [
        ec2.SecurityGroupRule(
            IpProtocol=p[0], CidrIp=DEFAULT_ROUTE, FromPort=p[1], ToPort=p[1]
        ) for p in [('tcp', 22), ('tcp', 80), ('tcp', 443)]
    ]

    security_group = template.add_resource(
        ec2.SecurityGroup(
            "JenkinsSecurityGroup",
            GroupDescription='Security Group for jenkins instances',
            VpcId=Ref(cfn.vpcs[0]),
            SecurityGroupIngress=ingress_rules,
            DependsOn=cfn.vpcs[0].title,
            Tags=Tags(Name='.'.join(['jenkins-sg', CLOUDNAME, CLOUDENV]))
        )
    )

    launch_cfg = template.add_resource(
        autoscaling.LaunchConfiguration(
            "JenkinsLaunchConfiguration",
            ImageId=FindInMap('RegionMap', Ref("AWS::Region"), int(cfn.Amis.EBS)),
            InstanceType=Ref(jenkins_instance_class),
            IamInstanceProfile=Ref(jenkins_instance_profile),
            AssociatePublicIpAddress=not USE_PRIVATE_SUBNETS,
            BlockDeviceMappings=[
                ec2.BlockDeviceMapping(
                    DeviceName='/dev/sda1',
                    Ebs=ec2.EBSBlockDevice(
                        DeleteOnTermination=True
                    )
                )
            ],
            KeyName=Ref(cfn.keyname),
            SecurityGroups=[Ref(security_group)],
            DependsOn=[jenkins_instance_profile.title, security_group.title],
            UserData=Base64(jenkins_user_data)
        )
    )

    asg_name = '.'.join(['jenkins', CLOUDNAME, CLOUDENV])
    asg = template.add_resource(
        autoscaling.AutoScalingGroup(
            "JenkinsASG",
            AvailabilityZones=cfn.get_asg_azs(),
            DesiredCapacity="1",
            LaunchConfigurationName=Ref(launch_cfg),
            MinSize="1",
            MaxSize="1",
            NotificationConfiguration=autoscaling.NotificationConfiguration(
                TopicARN=Ref(cfn.alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE,
                    EC2_INSTANCE_TERMINATE_ERROR,
                    EC2_INSTANCE_LAUNCH,
                    EC2_INSTANCE_LAUNCH_ERROR
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in cfn.get_vpc_subnets(cfn.vpcs[0], cfn.SubnetTypes.PLATFORM)]
        )
    )
