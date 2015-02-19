# `cloudformation`
Our experimental (and likely transient) cloudformation experiment.

# Why?

Basically, all existing tooling out there to orchestrate CloudFormation is too limited or doesn't support complex scenarios. That forces us to go straight to the cloudformation template.

This is just a bunch of Python scripts that use [`troposphere`](https://github.com/cloudtools/troposphere) to generate CloudFormation templates to get us in a situation to be able to work.

# Configuring Cloudformation Output

The `conf.py` file has some limited configuration options that you can specify (for stuff like name of the VPC and the `/16` CIDR block prefix you want, as well as whether or not subnets are private or public).

The configuration file is optional unncessary as default settings are specified in `config.py`.

# Building scripts

It's easiest to use `virtualenv` run this (so I don't pollute your environment).

    virtualenv venv
    source venv/bin/activate
    pip install -r requirements.pip

    # Run either of the next two commands
    python generate.py -o infra.template # accept the default specified at the top of config.py
    python generate.py -c conf.yml -o infra.template # specify a conf.yml file that overrides settings in config.py

This will generate an `infra.template` file that you can use for CloudFormation.
