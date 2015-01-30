import yaml

from troposphere import Parameter, Ref, Tags, Template
from troposphere import Join, Output, Select, FindInMap

from troposphere.ec2 import NetworkAcl, NetworkInterfaceProperty
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
from troposphere.ec2 import SecurityGroup, SecurityGroupRule
from troposphere.ec2 import Instance

with open ('conf.yml', 'r') as yfile:
    config = yaml.load(yfile)
    infra = config['infra'][0]

DEFAULT_ROUTE = '0.0.0.0/0'
CIDR_PREFIX= infra['network']['cidr_16_prefix']
VPC_NAME = infra['name']

t = Template()
t.add_version('2010-09-09')

t.add_description('This is a Cloudformation script that creates the base VPC across three AZs, with 1 public subnet, 3 private subnets, and proper NAT and routing tables.')

# Parameters for the Cloudformation Template
t.add_mapping('RegionMap',
    {
        'us-east-1': {'NATAMI': 'ami-184dc970'},
        'us-west-1': {'NATAMI': 'ami-a98396ec'},
        'us-west-2': {'NATAMI': 'ami-290f4119'},
        'eu-west-1': {'NATAMI': 'ami-14913f63'},
        'ap-northeast-1': { 'NATAMI': 'ami-27d6e626'},
        'ap-southeast-1': { 'NATAMI': 'ami-6aa38238'},
        'ap-southeast-2': { 'NATAMI': 'ami-893f53b3'},
    })

nat_instance_class = t.add_parameter(Parameter(
    'NatInstanceType', Type='String', Default='t2.micro',
    Description='NAT instance type',
    AllowedValues=['t2.micro', 't2.medium', 't2.medium', 'm3.medium',
                   'm3.large', 'm3.xlarge', 'c3.large', 'c3.xlarge'],
    ConstraintDescription='Instance size must be a valid instance type'
))

# An EC2 keypair to use
keyname_param = t.add_parameter(Parameter(
    'KeyName', Type='AWS::EC2::KeyPair::KeyName',
    Description='Name of an existing EC2 KeyPair to enable SSH access'
))

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

    private_subnets = list()

    # Create worker subnets
    worker_subnet = Subnet(
        '{0}PrivateWorkerSubnet{1}'.format(VPC_NAME, zone),
        VpcId=Ref(vpc),
        CidrBlock='{0}.{1}.0/22'.format(CIDR_PREFIX, 100 + (idx  * 4)),
        AvailabilityZone=full_region_descriptor,
        DependsOn=vpc.title,
        Tags=Tags(Name=Join('-', [VPC_NAME, 'private-worker-subnet', full_region_descriptor]))
    )

    private_subnets.append(worker_subnet)


    # Create the platform subnet
    platform_subnet = Subnet('{0}PrivatePlatformSubnet{1}'.format(VPC_NAME, zone.upper()),
        VpcId=Ref(vpc),
        CidrBlock='{0}.{1}.0/24'.format(CIDR_PREFIX, 10 + idx),
        AvailabilityZone=full_region_descriptor,
        DependsOn=vpc.title,
        Tags=Tags(Name=Join('-', [VPC_NAME, 'private-platform-subnet', full_region_descriptor]))
    )

    private_subnets.append(platform_subnet)

    # Create the master subnet
    master_subnet = Subnet('{0}PrivateMasterSubnet{1}'.format(VPC_NAME, zone.upper()),
        VpcId=Ref(vpc),
        CidrBlock='{0}.{1}.0/24'.format(CIDR_PREFIX, 90 + idx),
        AvailabilityZone=full_region_descriptor,
        DependsOn=vpc.title,
        Tags=Tags(Name=Join('-', [VPC_NAME, 'private-master-subnet', full_region_descriptor]))
    )

    private_subnets.append(master_subnet)

    # Associate every subnet with the private routing table
    for psn in private_subnets:
        t.add_resource(psn)
        t.add_resource(SubnetRouteTableAssociation(
            '{0}PrivateRouteTableAssociation'.format(psn.title),
            SubnetId=Ref(psn),
            RouteTableId=Ref(private_rt),
            DependsOn=psn.title
        ))

print(t.to_json())
