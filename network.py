import yaml
import argparse
import json

from troposphere import Parameter, Ref, Tags, Template, GetAtt
from troposphere import Join, Output, Select, FindInMap, Base64
from troposphere import Equals

from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, Tag
from troposphere.autoscaling import Metadata, NotificationConfiguration
from troposphere.autoscaling import EC2_INSTANCE_TERMINATE
from troposphere.cloudwatch import Alarm, MetricDimension
from troposphere.iam import Role, Group, PolicyType, LoginProfile, Policy, InstanceProfile
from troposphere.ec2 import NetworkAcl, NetworkInterfaceProperty
from troposphere.ec2 import BlockDeviceMapping, EBSBlockDevice
from troposphere.ec2 import Route
from troposphere.ec2 import SubnetRouteTableAssociation
from troposphere.ec2 import Subnet
from troposphere.ec2 import VPNConnectionRoute
from troposphere.ec2 import RouteTable
from troposphere.ec2 import VPC
from troposphere.ec2 import NetworkAclEntry
from troposphere.ec2 import VPNGateway
from troposphere.ec2 import SubnetNetworkAclAssociation
from troposphere.ec2 import VPNConnection
from troposphere.ec2 import InternetGateway
from troposphere.ec2 import VPCGatewayAttachment
from troposphere.ec2 import SecurityGroup, SecurityGroupRule, SecurityGroupIngress
from troposphere.ec2 import Instance
from troposphere.sqs import Queue, RedrivePolicy
from troposphere.sns import Topic, Subscription
from troposphere.s3 import Bucket

def _create_parser():
    parser = argparse.ArgumentParser(prog='network.py')
    parser.add_argument('-c', '--config', type=str, required=True, help='The configuration YAML file to use to generate the Cloudformation template')
    parser.add_argument('-o', '--outfile', type=str, help='The file to write the Cloudformation template to')
    return parser

def sanitize_id(*args):
    '''This sanitizes logical identifiers for Cloudformation as they are not allowed
    to have anything but [A-Za-z0-9]'''

    identifier = ''.join(args)
    return ''.join([c for c in identifier if c.isalnum()])


def create_cfn_template(conf_file, outfile):
    with open (conf_file, 'r') as yfile:
        config = yaml.load(yfile)
        infra = config['infra'][0]

    DEFAULT_ROUTE = '0.0.0.0/0'
    CIDR_PREFIX= infra['network']['cidr_16_prefix']
    CLOUDNAME = infra['cloudname']
    CLOUDENV = infra['env']
    USE_PRIVATE_SUBNETS = infra['network']['private_subnets']

    VPC_NAME = sanitize_id(CLOUDNAME, CLOUDENV)

    t = Template()
    t.add_version('2010-09-09')

    t.add_description('This is a Cloudformation script that creates the base VPC across three AZs, with 1 public subnet, 3 private subnets, and proper NAT and routing tables.')

    # Parameters for the Cloudformation Template
    t.add_mapping('RegionMap',
        {
            'us-east-1': {'NATAMI': 'ami-184dc970',
                          'EBSAMI': 'ami-86562dee',
                          'INSTANCESTOREAMI': 'ami-cc5229a4'},
            'us-west-1': {'NATAMI': 'ami-a98396ec'},
            'us-west-2': {'NATAMI': 'ami-290f4119'},
            'eu-west-1': {'NATAMI': 'ami-14913f63'},
            'ap-northeast-1': { 'NATAMI': 'ami-27d6e626'},
            'ap-southeast-1': { 'NATAMI': 'ami-6aa38238'},
            'ap-southeast-2': { 'NATAMI': 'ami-893f53b3'},
        })

    allowed_instance_values = ['t2.micro', 't2.medium', 't2.medium', 'm3.medium',
                       'm3.large', 'm3.xlarge', 'c3.large', 'c3.xlarge']


    nat_instance_class = t.add_parameter(Parameter(
        'NatInstanceType', Type='String', Default='t2.micro',
        Description='NAT instance type',
        AllowedValues=allowed_instance_values,
        ConstraintDescription='Instance size must be a valid instance type'
    ))

    babysitter_instance_class = t.add_parameter(Parameter(
        'BabysitterInstanceType', Type='String', Default='t2.micro',
        Description='Chef Babysitter instance type',
        AllowedValues=allowed_instance_values,
        ConstraintDescription='Instance size must be a valid instance type'
    ))

    zookeeper_instance_class = t.add_parameter(Parameter(
        'ZookeeperInstanceType', Type='String', Default='m3.medium',
        Description='Zookeeper instance type',
        AllowedValues=allowed_instance_values,
        ConstraintDescription='Instance size must be a valid instance type'
    ))

    create_cloudstrap_bucket = t.add_parameter(
        Parameter(
            'CreateCloudstrapBucket',
            Type='String',
            Description='Whether or not to create the Cloudstrap bucket',
            Default='no',
            AllowedValues=['yes', 'no'],
            ConstraintDescription='Answer must be yes or no'
        )
    )

    create_zookeeper_bucket = t.add_parameter(
        Parameter(
            'CreateZookeeperBucket',
            Type='String',
            Description='Whether or not to create the Zookeeper bucket. This option is provided in case the bucket already exists.',
            Default='no',
            AllowedValues=['yes', 'no'],
            ConstraintDescription='Answer must be yes or no'
        )
    )

    # An EC2 keypair to use
    keyname_param = t.add_parameter(Parameter(
        'KeyName', Type='AWS::EC2::KeyPair::KeyName',
        Description='Name of an existing EC2 KeyPair to enable SSH access'
    ))

    conditions = {
        "CloudstrapBucketCondition": Equals(
            Ref(create_cloudstrap_bucket), "yes"
        ),
        "ZookeeperBucketCondition": Equals(
            Ref(create_zookeeper_bucket), "yes"
        )
    }

    for c in conditions:
        t.add_condition(c, conditions[c])

    # Set the AZs this template creates resources in
    AVAILABILITY_ZONES = ['c', 'd', 'e']
    az_string = ','.join(AVAILABILITY_ZONES)
    availability_zones = t.add_parameter(Parameter(
        'AvailabilityZones', Type='CommaDelimitedList', Default=az_string,
        Description='A list of three availability zone letters to distribute the subnets across.'
    ))

    # The VPC
    vpc = t.add_resource(VPC(
        'VPC', CidrBlock='{0}.0.0/16'.format(CIDR_PREFIX), EnableDnsSupport=True,
        Tags=Tags(Name=Join('-', [VPC_NAME, Ref('AWS::Region')]))
    ))

    igw = t.add_resource(InternetGateway(
        'InternetGateway', Tags=Tags(Name='InternetGateway'),
        DependsOn=vpc.title
    ))

    gateway_attachment = t.add_resource(VPCGatewayAttachment(
        'GatewayAttachment', VpcId=Ref(vpc), InternetGatewayId=Ref(igw),
        DependsOn=igw.title
    ))

    public_rt = t.add_resource(RouteTable(
        '{0}PublicRouteTable'.format(VPC_NAME), VpcId=Ref(vpc),
        DependsOn=vpc.title
    ))

    # add in the public routes for this
    t.add_resource(Route('PublicRoute', RouteTableId=Ref(public_rt),
        DestinationCidrBlock=DEFAULT_ROUTE,
        DependsOn=gateway_attachment.title,
        GatewayId=Ref(igw),
    ))

    nat_ingress_rules = [
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp=DEFAULT_ROUTE, FromPort=p, ToPort=p
        ) for p in [22, 80, 443]
    ]

    nat_egress_rules = [
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp=DEFAULT_ROUTE, FromPort=p, ToPort=p
        ) for p in [80, 443]
    ]


    nat_sg = t.add_resource(SecurityGroup(
        "NATSecurityGroup",
        GroupDescription="Security Group for NAT instances",
        VpcId=Ref(vpc),
        SecurityGroupIngress=nat_ingress_rules,
        SecurityGroupEgress=nat_egress_rules,
        DependsOn=vpc.title
    ))

    # Add in a security group for SSH access from the internets
    ssh_ingress_rules = [
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp=DEFAULT_ROUTE, FromPort=p, ToPort=p
        ) for p in [22]
    ]

    ssh_sg = t.add_resource(SecurityGroup(
        "SSHAccessibleSecurityGroup",
        GroupDescription="Allow SSH access from public",
        VpcId=Ref(vpc),
        SecurityGroupIngress=ssh_ingress_rules,
        DependsOn=vpc.title,
        Tags=Tags(Name='.'.join(['ssh-accessible', CLOUDNAME, CLOUDENV]))
    ))


    zookeeper_sg = t.add_resource

    platform_subnets = list()
    master_subnets = list()

    for idx, zone in enumerate(AVAILABILITY_ZONES):
        region = Ref('AWS::Region')
        availability_zone = Select(idx, Ref(availability_zones))
        full_region_descriptor = Join('', [region, availability_zone])
        # create a public subnet in each availability zone
        public_subnet = t.add_resource(Subnet(
            '{0}PublicSubnet{1}'.format(VPC_NAME, zone),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(CIDR_PREFIX, 80 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [VPC_NAME, 'public-subnet', full_region_descriptor]))
        ))

        # Associate the public routing table with the subnet
        t.add_resource(SubnetRouteTableAssociation(
            '{0}PublicRouteTableAssociation'.format(public_subnet.title),
            SubnetId=Ref(public_subnet),
            RouteTableId=Ref(public_rt),
            DependsOn=public_subnet.title
        ))

        # Create the NAT in the public subnet
        nat_name = '{0}Nat{1}'.format(VPC_NAME, zone)
        nat_instance = t.add_resource(Instance(
            nat_name,
            DependsOn=vpc.title,
            InstanceType=Ref(nat_instance_class),
            KeyName=Ref(keyname_param),
            SourceDestCheck=False,
            ImageId=FindInMap('RegionMap', region, 'NATAMI'),
            NetworkInterfaces=[
                NetworkInterfaceProperty(
                    Description='Network interface for {0}'.format(nat_name),
                    GroupSet=[Ref(nat_sg)],
                    SubnetId=Ref(public_subnet),
                    AssociatePublicIpAddress=True,
                    DeviceIndex=0,
                    DeleteOnTermination=True
                )
            ],
            Tags=Tags(Name=Join('-', [VPC_NAME, 'nat', full_region_descriptor]))
        ))

        # Associate a private routing table with the NAT
        # and this AZ
        private_rt = t.add_resource(RouteTable(
            '{0}PrivateRouteTable{1}'.format(VPC_NAME, zone),
            VpcId=Ref(vpc),
            DependsOn=nat_instance.title,
            Tags=Tags(Name=Join('-', [VPC_NAME, 'private-route-table', full_region_descriptor]))
        ))

        # create routes for private routing table
        t.add_resource(Route('PrivateRoute{0}'.format(zone.upper()),
            RouteTableId=Ref(private_rt),
            DestinationCidrBlock=DEFAULT_ROUTE,
            InstanceId=Ref(nat_instance),
            DependsOn=private_rt.title
        ))

        subnets = list()

        subnet_identifier = 'private' if USE_PRIVATE_SUBNETS else 'public'

        # Create worker subnets
        worker_subnet = Subnet(
            '{0}{1}WorkerSubnet{2}'.format(VPC_NAME, subnet_identifier, zone),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/22'.format(CIDR_PREFIX, 100 + (idx  * 4)),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [VPC_NAME, '{0}-worker-subnet'.format(subnet_identifier), full_region_descriptor]))
        )

        subnets.append(worker_subnet)


        # Create the platform subnet
        platform_subnet = Subnet('{0}{1}PlatformSubnet{2}'.format(VPC_NAME, subnet_identifier, zone.upper()),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(CIDR_PREFIX, 10 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [VPC_NAME, '{0}-platform-subnet'.format(subnet_identifier), full_region_descriptor]))
        )

        subnets.append(platform_subnet)
        platform_subnets.append(platform_subnet)

        # Create the master subnet
        master_subnet = Subnet('{0}{1}MasterSubnet{2}'.format(VPC_NAME, subnet_identifier, zone.upper()),
            VpcId=Ref(vpc),
            CidrBlock='{0}.{1}.0/24'.format(CIDR_PREFIX, 90 + idx),
            AvailabilityZone=full_region_descriptor,
            DependsOn=vpc.title,
            Tags=Tags(Name=Join('-', [VPC_NAME, '{0}-master-subnet'.format(subnet_identifier), full_region_descriptor]))
        )

        subnets.append(master_subnet)
        master_subnets.append(master_subnet)

        # Associate every subnet with the private routing table
        routing_table = private_rt if USE_PRIVATE_SUBNETS else public_rt
        for psn in subnets:
            t.add_resource(psn)
            t.add_resource(SubnetRouteTableAssociation(
                '{0}{1}RouteTableAssociation'.format(psn.title, subnet_identifier),
                SubnetId=Ref(psn),
                RouteTableId=Ref(routing_table),
                DependsOn=psn.title
            ))


    # Build an S3 bucket for this region's Cloudstrap
    cloudstrap_bucket_name = Join('.', ['cloudstrap', CLOUDNAME, region, CLOUDENV, 'leafme'])
    cloudstrap_bucket = t.add_resource(
        Bucket("CloudstrapBucket",
            BucketName=cloudstrap_bucket_name,
            DeletionPolicy='Retain',
            Condition="CloudstrapBucketCondition"
        )
    )

    # Babysitter Stuff (monitoring instances for death)
    # Build an SQS Queue associated with every environment

    # Define a parameter for where alerts go
    babysitter_email_param = t.add_parameter(Parameter(
        'BabysitterAlarmEmail',
        Default='wlee@leaf.me',
        Description='Email address to notify if there are issues in the babysitter queue',
        Type='String'
    ))

    qname = '_'.join(['chef-deregistration', CLOUDNAME, CLOUDENV])
    queue = t.add_resource(Queue(sanitize_id(qname),
                VisibilityTimeout=60,
                MessageRetentionPeriod=1209600,
                MaximumMessageSize=16384,
                QueueName=qname,
            ))

    alert_topic = t.add_resource(
        Topic(
            "BabysitterAlarmTopic",
            DisplayName='Babysitter Alarm',
            TopicName=qname,
            Subscription=[
                Subscription(
                    Endpoint=Ref(babysitter_email_param),
                    Protocol='email'
                ),
            ],
            DependsOn=queue.title
        )
    )

    queue_depth_alarm = t.add_resource(
        Alarm(
            "BabysitterQueueDepthAlarm",
            AlarmDescription='Alarm if the queue depth grows beyond 200 messages',
            Namespace="AWS/SQS",
            MetricName="ApproximateNumberOfMessagesVisible",
            Dimensions=[
                MetricDimension(
                    Name="QueueName",
                    Value=GetAtt(queue, "QueueName")
                )
            ],
            Statistic="Sum",
            Period="300",
            EvaluationPeriods="1",
            Threshold="200",
            ComparisonOperator="GreaterThanThreshold",
            AlarmActions=[Ref(alert_topic), ],
            InsufficientDataActions=[Ref(alert_topic), ],
            DependsOn=alert_topic.title
        ),
    )

    # this is the standard  AssumeRolePolicyStatement block
    assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": [ "ec2.amazonaws.com" ]
                },
                "Action": ["sts:AssumeRole"],
            }]
        }

    # Create IAM role for the babysitter instance
    # load the policies
    with open('babysitter_policy.json', 'r') as bsp, open('default_policy.json', 'r') as dp:
        babysitter_policy = json.load(bsp)
        default_policy = json.load(dp)

    babysitter_role_name = '.'.join(['babysitter', CLOUDNAME, CLOUDENV])
    babysitter_iam_role = t.add_resource(
        Role(
            "BabysitterIamRole",
            AssumeRolePolicyDocument=assume_role_policy,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="BabySitterPolicy",
                    PolicyDocument=babysitter_policy
                ),
                Policy(
                    PolicyName="BabySitterDefaultPolicy",
                    PolicyDocument=default_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    babysitter_instance_profile = t.add_resource(
        InstanceProfile(
            "babysitterInstanceProfile",
            Path="/",
            Roles=[Ref(babysitter_iam_role)],
            DependsOn=babysitter_iam_role.title
        )
    )


    with open('cloud-init.bash', 'r') as shfile:
        bash_file = shfile.read()

    # Create babysitter launch configuration
    babysitter_launchcfg = t.add_resource(
        LaunchConfiguration(
            "BabysitterLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, 'EBSAMI'),
            InstanceType=Ref(babysitter_instance_class),
            IamInstanceProfile=Ref(babysitter_instance_profile),
            BlockDeviceMappings=[
                BlockDeviceMapping(
                    DeviceName="/dev/sda1",
                    Ebs=EBSBlockDevice(
                        DeleteOnTermination=True
                    )
                )
            ],
            KeyName=Ref(keyname_param),
            SecurityGroups=[Ref(ssh_sg)],
            DependsOn=[babysitter_instance_profile.title, ssh_sg.title],
            UserData=Base64(bash_file)
        )
    )

    asg_azs = [Join('', [Ref('AWS::Region'), az]) for az in AVAILABILITY_ZONES]

    # Create the babysitter autoscaling group
    babysitter_asg_name = '.'.join(['babysitter', CLOUDNAME, CLOUDENV])
    babysitter_asg = t.add_resource(
        AutoScalingGroup(
            "BabysitterASG",
            AvailabilityZones=asg_azs,
            DesiredCapacity="1",
            LaunchConfigurationName=Ref(babysitter_launchcfg),
            MinSize="1",
            MaxSize="1",
            NotificationConfiguration=NotificationConfiguration(
                TopicARN=Ref(alert_topic),
                NotificationTypes=[
                    EC2_INSTANCE_TERMINATE
                ]
            ),
            VPCZoneIdentifier=[Ref(sn) for sn in platform_subnets]
        )
    )

    # Zookeeper stuff!
    # BEGIN ZOOKEPER
    zookeeper_ingress_rules = [
        SecurityGroupRule(
            IpProtocol='tcp', CidrIp='{0}.0.0/16'.format(CIDR_PREFIX), FromPort=p, ToPort=p
        ) for p in [2181]
    ]

    zookeeper_sg = t.add_resource(
        SecurityGroup(
            "ZookeeperSecurityGroup",
            GroupDescription="Security Group for ZooKeeper instances",
            VpcId=Ref(vpc),
            SecurityGroupIngress=zookeeper_ingress_rules,
            DependsOn=vpc.title
        )
    )

    # Now add in another ingress rule that allows zookeepers to talk to each other
    # in the same SG
    for port in [2888, 3888]:
        t.add_resource(
            SecurityGroupIngress(
                "ZookeeperSelfIngress{0}".format(port),
                IpProtocol='tcp',
                FromPort=port,
                ToPort=port,
                GroupId=Ref(zookeeper_sg),
                SourceSecurityGroupId=Ref(zookeeper_sg),
                DependsOn=zookeeper_sg.title
            )
        )

    # Create the zookeeper s3 bucket
    zookeeper_bucket_name = Join('.', ['zookeeper', CLOUDNAME, region, CLOUDENV, 'leafme'])
    cloudstrap_bucket = t.add_resource(
        Bucket(
            "ZookeeperBucket",
            BucketName=zookeeper_bucket_name,
            DeletionPolicy='Retain',
            Condition="ZookeeperBucketCondition"
        )
    )

    # IAM role for zookeeper
    with open('zookeeper_policy.json', 'r') as zkp:
        zookeeper_policy = json.load(zkp)

    zookeeper_role_name = '.'.join(['zookeeper', CLOUDNAME, CLOUDENV])
    zookeeper_iam_role = t.add_resource(
        Role(
            "ZookeeperIamRole",
            AssumeRolePolicyDocument=assume_role_policy,
            Path="/",
            Policies=[
                Policy(
                    PolicyName="ZookeeperDefaultPolicy",
                    PolicyDocument=default_policy
                ),
                Policy(
                    PolicyName="ZookeeperPolicy",
                    PolicyDocument=zookeeper_policy
                )
            ],
            DependsOn=vpc.title
        )
    )

    zookeeper_instance_profile = t.add_resource(
        InstanceProfile(
            "zookeeperInstanceProfile",
            Path="/",
            Roles=[Ref(zookeeper_iam_role)],
            DependsOn=zookeeper_iam_role.title
        )
    )

    # Launch Configuration for zookeepers
    zookeeper_launchcfg = t.add_resource(
        LaunchConfiguration(
            "ZookeeperLaunchConfiguration",
            ImageId=FindInMap('RegionMap', region, 'INSTANCESTOREAMI'),
            InstanceType=Ref(zookeeper_instance_class),
            IamInstanceProfile=Ref(zookeeper_instance_profile),
            KeyName=Ref(keyname_param),
            SecurityGroups=[Ref(zookeeper_sg), Ref(ssh_sg)],
            DependsOn=[zookeeper_instance_profile.title, zookeeper_sg.title, zookeeper_sg.title, ssh_sg.title]
        )
    )

    # Create the babysitter autoscaling group
    zookeeper_asg_name = '.'.join(['zookeeper', CLOUDNAME, CLOUDENV])
    zookeeper_asg = t.add_resource(
        AutoScalingGroup(
            "ZookeeperASG",
            AvailabilityZones=asg_azs,
            DesiredCapacity="3",
            LaunchConfigurationName=Ref(zookeeper_launchcfg),
            MinSize="3",
            MaxSize="3",
            VPCZoneIdentifier=[Ref(sn) for sn in master_subnets]
        )
    )


    # END ZOOKEEPER

    if not outfile:
        print(t.to_json())
    else:
        with open(outfile, 'w') as ofile:
            print >> ofile, t.to_json()

if __name__ == '__main__':
    arg_parser = _create_parser()
    args = arg_parser.parse_args()

    print('Creating cloudformation template using config file: {0} '.format(args.config))
    create_cfn_template(args.config, args.outfile)
