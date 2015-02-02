with ENV = [infra, sandbox, staging, prod]
with REGION = [us-east-1, us-west-1, us-west-2]

with BUCKET = ENV.REGION.CLOUDNAME.instance.cloudstrap.leafme

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

- Create S3 bucket `BUCKET`.
  - Upload `s3://BUCKET/validator.pem` to bucket. (If hosted-chef, will be named `leaf-ENV-validator.pem`, change it.)
  - Upload VPN server credentials to `s3://BUCKET/vpn-server`
- Create security group `ENV.CLOUDNAME.ssh-accessible`.
  - ingress for `/0`: tcp 22 (TODO: change to VPN subnet when VPN working)

## Networks
- We've already got this. `platform`, `master`, `worker`, and `public` subnets.

## Babysitter
- Create SQS queue `ENV_CLOUDNAME_chef-deregistration`.
  - Visibility timeout: 1 minute
  - Retention period: 14 days
  - Message size: 16 kilobytes
- Create SNS queue `ENV_CLOUDNAME_chef-deregistration`.
- Subscribe SQS queue to SNS queue.
- Create IAM role `ENV.CLOUDNAME.babysitter`.
  - Apply `default_policy.json.erb` to role.
  - Apply `babysitter_policy.json.erb` to role.
- Create launch configuration `ENV.CLOUDNAME.babysitter`:
  - `t2.micro`
  - EBS delete on termination
  - compute user data like so:
```bash
erber -o env=infra -o cloud=test-cloud -o deploy=babysitter lib/templates/cloud-init.bash.erb
```
- Create autoscaling group `ENV.CLOUDNAME.babysitter`
  - 1 instance
  - Add it. (Chef will do the rest.)

## Zookeeper
- Create IAM role `ENV.CLOUDNAME.zookeeper`.
  - Apply `DEFAULT_POLICY` to role.
- Create security group `ENV.CLOUDNAME.zookeeper`.
  - ingress for `VPC-CIDR/16`: tcp 2181
  - ingress for `ENV.CLOUDNAME.zookeeper`: tcp 2888, tcp 3888