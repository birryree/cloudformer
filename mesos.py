#!/usr/bin/env python
# -*- coding: utf-8 -*-

import yaml
import argparse
import json
import os
import subprocess

from troposphere import Parameter

import config as cfn

def emit_configuration():
    mesos_instance_class = cfn.template.add_parameter(
        Parameter

    mesos_security_group = cfn.template.add_resource(
        SecurityGroup(
            "MesosSecurityGroup",
            GroupDescription="Security Group for Mesos instances",
            VpcId=Ref(vpc),

    mesos_ingress_rules = [
        SecurityGroupRule(
            IpProtocol
