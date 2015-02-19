with ENV = [infra, sandbox, staging, prod]
with REGION = [us-east-1, us-west-1, us-west-2]

with CLOUDSTRAP_BUCKET = cloudstrap.CLOUDNAME.REGION.ENV.leafme

## General
- Install `knife`, `berkshelf`, and `erber` from Rubygems.
- Have a Chef server. Hosted or not.
  - Create a Chef environment, `ENV.CLOUDNAME`. You can get an `environment.rb` like this:
```bash
erber -o env=infra -o cloud=test-cloud lib/templates/environment.rb.erb > environment.rb
```

- Default policy DEFAULT_POLICY (`lib/templates/default_policy.json.erb`):
```bash
erber -o env=infra -o cloud=test-cloud -o region=us-east-1 lib/templates/default_policy.json.erb
```

- Create S3 bucket `CLOUDSTRAP_BUCKET`.
  - Upload `s3://CLOUDSTRAP_BUCKET/chef-server-bootstrap.tar.gz`, containing the `chef-solo` cookbook to install `chef-server`. 
  - Upload `s3://CLOUDSTRAP_BUCKET/chef-github.pem`, containing a private key okayed for use with a readonly Chef account.
  - Upload `s3://CLOUDSTRAP_BUCKET/validator.pem` to bucket. (If hosted-chef, will be named `leaf-ENV-validator.pem`, change it.)
  - Upload VPN server credentials to `s3://BUCKET/vpn-server`
- Create security group `ssh-accessible.CLOUDNAME.ENV`.
  - ingress for `/0`: tcp 22 (TODO: change to VPN subnet when VPN working)

## Networks
- We've already got this. `platform`, `master`, `worker`, and `public` subnets.

## Babysitter
- Create SQS queue `chef-deregistration_CLOUDNAME_ENV`.
  - Visibility timeout: 1 minute
  - Retention period: 14 days
  - Message size: 16 kilobytes
- Set a cloudwatch alarm on the SQS queue if it gets over, say, 200 entries.
- Create SNS queue `chef-deregistration_CLOUDNAME_ENV`.
- Subscribe SQS queue to SNS queue.
- Create IAM role `babysitter.CLOUDNAME.ENV`.
  - Apply `default_policy.json.erb` to role.
  - Apply `babysitter_policy.json.erb` to role.
- Create launch configuration `babysitter.CLOUDNAME.ENV`:
  - `t2.micro`
  - AMI: HVM EBS Ubuntu 14.04
  - EBS delete on termination
  - compute user data like so:
```bash
erber -o env=infra -o cloud=test-cloud -o deploy=babysitter lib/templates/cloud-init.bash.erb
```
- Create autoscaling group `babysitter.CLOUDNAME.ENV`
  - 1 instance
  - Subscribe `terminate` notices to SNS topic `chef-deregistration_CLOUDNAME_ENV`.
  - Add it. (Chef will do the rest.)
- `TODO:` write up the deregistration gizmo. 

## Zookeeper
- Create S3 bucket `zookeeper.CLOUDNAME.REGION.ENV.leafme`.
  - Ensure that the contents of `lib/templates/exhibitor.properties.erb` are stored in `s3://zookeeper.CLOUDNAME.REGION.ENV.leafme/exhibitor/primary`.
- Create IAM role `zookeeper.CLOUDNAME.ENV`.
  - Apply `default_policy.json.erb` to role.
  - Apply `zookeeper_policy.json.erb` to role.
- Create security group `zookeeper.CLOUDNAME.ENV`.
  - ingress for `VPC-CIDR/16`: tcp 2181
  - ingress for `ENV.CLOUDNAME.zookeeper`: tcp 2888, tcp 3888
- Create launch configuration `zookeeper.CLOUDNAME.ENV`:
  - `m3.large`
  - AMI: HVM Instance Store 14.04 (us-east-1: ami-1f958c76)
  - Security groups: `zookeeper.CLOUDNAME.ENV`, `ssh-accessible.CLOUDNAME.ENV`
