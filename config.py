#!/usr/bin/env python
# -*- coding: utf-8 -*-

from troposphere import Template

DEFAULT_ROUTE = '0.0.0.0/0'

ALLOWED_INSTANCE_SIZES = ['t2.micro', 't2.small', 't2.medium', 'm3.medium',
        'm3.large', 'm3.xlarge', 'm3.2xlarge', 'c3.large', 'c3.xlarge', 'c3.2xlarge']

def enum(**enums):
    return type('Enum', (), enums)

Amis = enum(NAT='nat', EBS='ebs', INSTANCE='instance')

# Initialize the Cloudformation template
template = Template()
template.add_version('2010-09-09')
template.add_description('This is a cloudformation script that creates our specific VPCs. Each VPC spans 3 availability zones.')

# These are all Ubuntu 14.04 AMIs (see: http://cloud-images.ubuntu.com/locator/ec2/)
template.add_mapping('RegionMap',
        {
            'us-east-1': {Amis.NAT: 'ami-184dc970',
                          Amis.EBS: 'ami-86562dee',
                          Amis.INSTANCE: 'ami-cc5229a4'},
            'us-west-1': {Amis.NAT: 'ami-a98396ec'},
            'us-west-2': {Amis.NAT: 'ami-290f4119'},
            'eu-west-1': {Amis.NAT: 'ami-14913f63'},
            'ap-northeast-1': {Amis.NAT: 'ami-27d6e626'},
            'ap-southeast-1': {Amis.NAT: 'ami-6aa38238'},
            'ap-southeast-2': {Amis.NAT: 'ami-893f53b3'},
        }
)


# This is a list of VPCs that will be used by cloudformation
vpcs = list()

# This is a mapping of VPCs to their own total state (so that we can emit the
# entire state of multiple clouds bound by VPC).
vpc_state = {}

def sanitize_id(*args):



class CloudState(object):
    _state = {}
    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        self.__dict__ = cls._state
        return self

