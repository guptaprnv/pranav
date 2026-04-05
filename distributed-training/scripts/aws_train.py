"""
aws_train.py — Launch a g4dn.xlarge EC2 instance, run 5-min ResNet-50
training on CIFAR-10, stream logs back, then terminate the instance.

Usage:
    python scripts/aws_train.py [--minutes 5] [--region us-east-1]

Cost estimate:
    g4dn.xlarge on-demand: $0.526/hr → ~$0.044 for 5 minutes
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import textwrap
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# ── Config ────────────────────────────────────────────────────────────────────
INSTANCE_TYPE   = "g4dn.xlarge"
AMI_ID_MAP = {
    # Deep Learning AMI (Ubuntu 22.04) — PyTorch 2.x pre-installed
    # Update these IDs if they expire: https://aws.amazon.com/releasenotes/aws-deep-learning-amis/
    "us-east-1":      "ami-0c5cce1d70efbae95",
    "us-east-2":      "ami-0d1f2e6b4c95a5e02",
    "us-west-2":      "ami-0e4d1886bf4bb88d5",
    "eu-west-1":      "ami-07b0b1f4b5c96a5a4",
    "ap-southeast-1": "ami-0a14f98d8f5b62921",
}
FALLBACK_AMI_SEARCH_NAME = "Deep Learning AMI GPU PyTorch 2* (Ubuntu 22.04)*"
SG_NAME       = "dtrain-5min-sg"
KEY_NAME_ENV  = "DT_AWS_KEY_NAME"    # optional: set to use SSH instead of SSM


def get_or_create_security_group(ec2, region: str) -> str:
    """Create (or reuse) a minimal security group — outbound only."""
    try:
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [SG_NAME]}]
        )["SecurityGroups"]
        if sgs:
            sg_id = sgs[0]["GroupId"]
            print(f"  ✓ Reusing security group: {sg_id}")
            return sg_id
    except ClientError:
        pass

    sg = ec2.create_security_group(
        GroupName=SG_NAME,
        Description="DTrain 5-min training — outbound only",
    )
    sg_id = sg["GroupId"]
    # No inbound rules needed — SSM agent handles management traffic
    print(f"  ✓ Created security group: {sg_id}")
    return sg_id


def find_ami(ec2, region: str) -> str:
    """Find the latest Deep Learning AMI for the region."""
    # Try region-specific known AMI first
    known = AMI_ID_MAP.get(region)
    if known:
        try:
            ec2.describe_images(ImageIds=[known])
            return known
        except ClientError:
            pass  # AMI not found in this account/region, fall through

    # Search for latest DLAMI
    resp = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name",              "Values": [FALLBACK_AMI_SEARCH_NAME]},
            {"Name": "state",             "Values": ["available"]},
            {"Name": "architecture",      "Values": ["x86_64"]},
            {"Name": "root-device-type",  "Values": ["ebs"]},
        ],
    )
    images = sorted(resp["Images"], key=lambda x: x["CreationDate"], reverse=True)
    if not images:
        raise RuntimeError(
            f"No Deep Learning AMI found in {region}. "
            "Try us-east-1 or check: https://aws.amazon.com/releasenotes/aws-deep-learning-amis/"
        )
    ami_id = images[0]["ImageId"]
    print(f"  ✓ Using AMI: {ami_id} ({images[0]['Name'][:60]})")
    return ami_id


def get_or_create_iam_profile(iam) -> str:
    """
    Create an IAM instance profile with SSM + S3 access
    so the instance can be managed without SSH.
    """
    profile_name = "dtrain-ec2-profile"
    role_name    = "dtrain-ec2-role"

    # Check if profile already exists
    try:
        iam.get_instance_profile(InstanceProfileName=profile_name)
        print(f"  ✓ IAM profile exists: {profile_name}")
        return profile_name
    except ClientError as e:
        if "NoSuchEntity" not in str(e):
            raise

    # Create role
    try:
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            }),
        )
        for policy in [
            "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",
        ]:
            iam.attach_role_policy(RoleName=role_name, PolicyArn=policy)
    except ClientError as e:
        if "EntityAlreadyExists" not in str(e):
            raise

    # Create profile and attach role
    try:
        iam.create_instance_profile(InstanceProfileName=profile_name)
        iam.add_role_to_instance_profile(
            InstanceProfileName=profile_name, RoleName=role_name
        )
        time.sleep(10)  # IAM propagation delay
    except ClientError as e:
        if "EntityAlreadyExists" not in str(e):
            raise

    print(f"  ✓ Created IAM profile: {profile_name}")
    return profile_name


def make_user_data(minutes: int, model: str, dataset: str) -> str:
    """
    EC2 UserData script — runs as root at instance launch.
    Installs the repo + deps, then runs training for `minutes` minutes.
    """
    script = f"""#!/bin/bash
set -e
exec > /var/log/dtrain.log 2>&1

echo "=== DTrain 5-min training started at $(date) ==="

# Activate PyTorch conda env (pre-installed on DLAMI)
source /opt/conda/etc/profile.d/conda.sh
conda activate pytorch

# Clone repo
cd /home/ubuntu
git clone https://github.com/guptaprnv/pranav.git repo || true
cd repo/distributed-training

# Install deps
pip install --quiet -r requirements.txt

# Run training — exits after {minutes} minutes
echo "=== Starting training: {model} on {dataset} for {minutes} min ==="
python -m src.train \\
    --config configs/small.yaml \\
    --max_minutes {minutes} \\
    --job_id aws-5min-$(date +%s)

echo "=== Training complete at $(date) ==="

# Signal completion
touch /tmp/training_done
"""
    return base64.b64encode(script.encode()).decode()


def wait_for_log(ssm, instance_id: str, timeout: int = 600) -> None:
    """Poll /var/log/dtrain.log via SSM Run Command and stream output."""
    print("\n  Streaming training logs (Ctrl+C to detach, instance keeps running):\n")
    print("  " + "─" * 60)

    seen_lines = 0
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            resp = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [
                    f"tail -n +{seen_lines + 1} /var/log/dtrain.log 2>/dev/null || true",
                    "test -f /tmp/training_done && echo '__DONE__' || true",
                ]},
            )
            cmd_id = resp["Command"]["CommandId"]
            time.sleep(3)

            out = ssm.get_command_invocation(
                CommandId=cmd_id, InstanceId=instance_id
            )
            stdout = out.get("StandardOutputContent", "")
            if stdout:
                lines = stdout.splitlines()
                for line in lines:
                    if line != "__DONE__":
                        print(f"  {line}")
                        seen_lines += 1
                if "__DONE__" in stdout:
                    print("\n  " + "─" * 60)
                    print("  ✓ Training completed successfully!")
                    return
        except ClientError as e:
            if "InvalidInstanceId" in str(e):
                time.sleep(10)   # instance not registered with SSM yet
                continue
            raise
        except KeyboardInterrupt:
            print("\n  Detached from logs. Instance is still running.")
            return
        time.sleep(10)

    print("\n  ⚠ Log stream timed out — training may still be running.")


def terminate(ec2, instance_id: str) -> None:
    ec2.terminate_instances(InstanceIds=[instance_id])
    print(f"  ✓ Instance {instance_id} terminated")


def main():
    parser = argparse.ArgumentParser(description="Launch 5-min AWS training job")
    parser.add_argument("--minutes",  type=int,   default=5,          help="Training time limit")
    parser.add_argument("--region",   default="us-east-1",            help="AWS region")
    parser.add_argument("--model",    default="resnet50",              help="Model name")
    parser.add_argument("--dataset",  default="cifar10",               help="Dataset")
    parser.add_argument("--no-terminate", action="store_true",
                        help="Don't terminate the instance after training (for debugging)")
    args = parser.parse_args()

    print(f"""
  ╔══════════════════════════════════════════════════╗
  ║  DTrain — AWS {args.minutes}-Minute Training Run            ║
  ║  Model:    {args.model:<38} ║
  ║  Dataset:  {args.dataset:<38} ║
  ║  Instance: {INSTANCE_TYPE:<38} ║
  ║  Region:   {args.region:<38} ║
  ║  Cost est: ~${args.minutes * 0.526 / 60:.3f} (g4dn.xlarge on-demand)       ║
  ╚══════════════════════════════════════════════════╝
""")

    # ── Boto3 clients ──────────────────────────────────────────────────────
    try:
        session = boto3.Session(region_name=args.region)
        ec2  = session.client("ec2")
        iam  = session.client("iam")
        ssm  = session.client("ssm")
        sts  = session.client("sts")

        identity = sts.get_caller_identity()
        print(f"  ✓ AWS account: {identity['Account']} ({args.region})")
    except NoCredentialsError:
        print("  ✗ No AWS credentials found. Run: make aws-setup")
        sys.exit(1)

    instance_id = None
    try:
        # ── IAM profile ───────────────────────────────────────────────────
        print("\n  Setting up IAM…")
        profile_name = get_or_create_iam_profile(iam)

        # ── AMI ────────────────────────────────────────────────────────────
        print("\n  Finding Deep Learning AMI…")
        ami_id = find_ami(ec2, args.region)

        # ── Security group ─────────────────────────────────────────────────
        print("\n  Configuring security group…")
        sg_id = get_or_create_security_group(ec2, args.region)

        # ── Launch instance ────────────────────────────────────────────────
        print(f"\n  Launching {INSTANCE_TYPE}…")
        launch_params = dict(
            ImageId=ami_id,
            InstanceType=INSTANCE_TYPE,
            MinCount=1,
            MaxCount=1,
            UserData=make_user_data(args.minutes, args.model, args.dataset),
            SecurityGroupIds=[sg_id],
            IamInstanceProfile={"Name": profile_name},
            InstanceInitiatedShutdownBehavior="terminate",
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name",    "Value": f"dtrain-5min-{int(time.time())}"},
                    {"Key": "Project", "Value": "distributed-training"},
                    {"Key": "AutoTerminate", "Value": "true"},
                ],
            }],
            BlockDeviceMappings=[{
                "DeviceName": "/dev/sda1",
                "Ebs": {"VolumeSize": 50, "VolumeType": "gp3", "DeleteOnTermination": True},
            }],
        )

        # Use spot instance for ~70% cost saving (optional)
        use_spot = os.environ.get("DT_USE_SPOT", "0") == "1"
        if use_spot:
            launch_params["InstanceMarketOptions"] = {
                "MarketType": "spot",
                "SpotOptions": {"SpotInstanceType": "one-time"},
            }
            print("  (using Spot instance — 70% cheaper, may be interrupted)")

        resp = ec2.run_instances(**launch_params)
        instance_id = resp["Instances"][0]["InstanceId"]
        print(f"  ✓ Instance launched: {instance_id}")

        # ── Wait for running ───────────────────────────────────────────────
        print("  Waiting for instance to reach 'running' state…")
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])

        instance_info = ec2.describe_instances(InstanceIds=[instance_id])
        pub_ip = instance_info["Reservations"][0]["Instances"][0].get("PublicIpAddress", "N/A")
        print(f"  ✓ Instance running: {pub_ip}")
        print(f"\n  Waiting for SSM agent and training to start (~2-3 min)…")
        time.sleep(90)   # DLAMI boot + conda env activation

        # ── Stream logs ────────────────────────────────────────────────────
        wait_for_log(ssm, instance_id, timeout=(args.minutes + 5) * 60)

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    except Exception as e:
        print(f"\n  ✗ Error: {e}")
        raise
    finally:
        if instance_id and not args.no_terminate:
            print(f"\n  Terminating instance {instance_id}…")
            try:
                terminate(ec2, instance_id)
            except Exception as e:
                print(f"  ⚠ Could not terminate: {e}")
                print(f"  Terminate manually: aws ec2 terminate-instances --instance-ids {instance_id}")
        elif instance_id and args.no_terminate:
            print(f"\n  Instance NOT terminated (--no-terminate flag).")
            print(f"  Terminate manually: aws ec2 terminate-instances --instance-ids {instance_id} --region {args.region}")

    print("\n  Done. Check your Mac mini dashboard or iPad app for results.")


if __name__ == "__main__":
    main()
