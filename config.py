#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import yaml
from collections import defaultdict

import jinja2
from enum import IntEnum
from troposphere import Template, Join, Ref


def sanitize_id(*args):
    '''This sanitizes logical identifiers for Cloudformation as they are not allowed
    to have anything but [A-Za-z0-9]

    Arguments:
        args - a variadic list of strings/stringifiable objects'''

    identifier = ''.join(args)
    return ''.join([c for c in identifier if c.isalnum()])


# These are default (sane-ish) values
# TODO: we really need to restrict our security groups, right now they're all DEFAULT_ROUTE
DEFAULT_ROUTE = '0.0.0.0/0'
CIDR_PREFIX = '10.151'
CLOUDNAME = 'test-cloud'
CLOUDENV = 'infra'
REGION = 'us-west-2'
USE_PRIVATE_SUBNETS = True
VPC_NAME = sanitize_id(CLOUDNAME, CLOUDENV)


def initialize(config):
    global CIDR_PREFIX
    global CLOUDNAME
    global CLOUDENV
    global USE_PRIVATE_SUBNETS
    global REGION
    global VPC_NAME
    infra = config['infra'][0]

    CIDR_PREFIX = infra['network']['cidr_16_prefix']
    CLOUDNAME = infra['cloudname']
    CLOUDENV = infra['env']
    USE_PRIVATE_SUBNETS = infra['network']['private_subnets']
    REGION = infra['region']
    VPC_NAME = sanitize_id(CLOUDNAME, CLOUDENV)


ASSUME_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {
            "Service": ["ec2.amazonaws.com"]
        },
        "Action": ["sts:AssumeRole"],
    }]
}

ALLOWED_INSTANCE_SIZES = ['t2.micro', 't2.small', 't2.medium', 'm3.medium',
        'm3.large', 'm3.xlarge', 'm3.2xlarge', 'c3.large', 'c3.xlarge', 'c3.2xlarge']

def usable_instances():
    """Retrieve list of AWS instance sizes that can be used"""
    return ALLOWED_INSTANCE_SIZES

Amis = IntEnum('Amis', 'NAT EBS INSTANCE')
SubnetTypes = IntEnum('SubnetTypes', 'PUBLIC PLATFORM WORKER VPN MASTER DATABASE')

# This is just hardcoded in right now, and really only fits us-east-1's mold
availability_zones = ['a', 'b', 'c']

def get_availability_zones():
    return availability_zones

def get_asg_azs():
    return [Join('', [Ref('AWS::Region'), az]) for az in availability_zones]

# Initialize the Cloudformation template
template = Template()
template.add_version('2010-09-09')
template.add_description('This is a cloudformation script that creates our specific VPCs. Each VPC spans 3 availability zones.')

# These are all Ubuntu 14.04 AMIs (see: http://cloud-images.ubuntu.com/locator/ec2/)
template.add_mapping('RegionMap',
        {
            'us-east-1': {int(Amis.NAT): 'ami-184dc970',
                          int(Amis.EBS): 'ami-86562dee',
                          int(Amis.INSTANCE): 'ami-cc5229a4'},
            'us-west-1': {int(Amis.NAT): 'ami-a98396ec'},
            'us-west-2': {int(Amis.NAT): 'ami-290f4119',
                          int(Amis.EBS): 'ami-51526761',
                          int(Amis.INSTANCE): 'ami-6d53665d'},
            'eu-west-1': {int(Amis.NAT): 'ami-14913f63'},
            'ap-northeast-1': {int(Amis.NAT): 'ami-27d6e626'},
            'ap-southeast-1': {int(Amis.NAT): 'ami-6aa38238'},
            'ap-southeast-2': {int(Amis.NAT): 'ami-893f53b3'},
        }
)

keyname = None

def load_template(filename, vardict):
    """Loads a template from the filesystem and renders it with variables replaced"""
    j2env = jinja2.Environment(loader=jinja2.FileSystemLoader('{0}/lib/templates'.format(
        os.path.dirname(__file__),
        trim_blocks=True
    )))
    return j2env.get_template(filename).render(vardict)


# This is a list of VPCs that will be used by cloudformation
vpcs = list()

# This is a mapping of VPCs to their own total state (so that we can emit the
# entire state of multiple clouds bound by VPC).
vpc_subnets = defaultdict(lambda: defaultdict(list))

# The SNS topic that will be used to alert of instance termination
alert_topic = None


def add_vpc_subnets(vpc, identifier, subnets):
    """Associate subnets with a VPC based on the subnet type"""
    vpc_subnets[vpc][identifier] = subnets


def get_vpc_subnets(vpc, identifier):
    """Retrieve subnets associated with a specific VPC"""
    return tuple(vpc_subnets[vpc][identifier])


class CloudState(object):
    _state = {}
    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        self.__dict__ = cls._state
        return self

