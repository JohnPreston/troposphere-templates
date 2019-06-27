#!/usr/bin/env python


import boto3

from datetime import datetime as dt
from troposphere import (
    Template, Parameter,
    GetAtt, Ref, Sub, Join
)

from troposphere import (
    If, Condition, Equals, Not
)

from troposphere.ec2 import (
    Instance,
    Volume, VolumeAttachment, MountPoint
)

from string import (
    ascii_lowercase as alpha,
    ascii_uppercase as ALPHA
)

from troposphere.cloudformation import (
    WaitCondition, WaitConditionHandle
)

from troposphere import (
    cloudformation,
    Base64
)

DISK_TYPES = [
    'gp2',
    'st1'
]

TYPES = boto3.client(
    'pricing',
    region_name='us-east-1'
).get_attribute_values(
    ServiceCode="AmazonEC2",
    AttributeName='InstanceType'
)['AttributeValues']

for count, ec2type in enumerate(TYPES):
    if ec2type['Value'].find('.') < 0:
        TYPES.pop(count)
    TYPES[count]['Value'] = TYPES[count]['Value'].lower()

EC2_TYPES = [ec2type['Value'] for ec2type in TYPES]


TPL = Template('Simple template for EC2 instance with multiple Disks')
TPL.set_metadata({
    'Author': 'https://github.com/johnpreston',
    'Date': dt.utcnow().isoformat()
})

RAID_DISK_TYPE = TPL.add_parameter(Parameter(
    'RaidDisksType',
    Type='String',
    AllowedValues=DISK_TYPES
))

RAID_DISK_SIZE = TPL.add_parameter(Parameter(
    'RaidDiskSize',
    Type='Number',
    MinValue=8,
    MaxValue=4069
))


CACHE_DISK_TYPE = TPL.add_parameter(Parameter(
    'CacheDiskType',
    Type='String',
    AllowedValues=DISK_TYPES
))

CACHE_DISK_SIZE = TPL.add_parameter(Parameter(
    'CacheDiskSize',
    Type='Number',
    MinValue=8,
    MaxValue=4069
))

USE_CACHE_DISK = TPL.add_parameter(Parameter(
    'UseCacheDisk',
    Type='String',
    AllowedValues=[
        'True',
        'False'
    ],
    Default='True'
))

ENCRYPTION_KEY_ID = TPL.add_parameter(Parameter(
    'KmsKeyId',
    Default='default',
    Type='String',
    AllowedPattern=r'((^default$)|([a-z0-9]{8})-([a-z0-9]{4})-([a-z0-9]{4})-([a-z0-9]{4})-([a-z0-9]{12}))'
))

INSTANCE_TYPE = TPL.add_parameter(Parameter(
    'InstanceType',
    Type='String',
    AllowedValues=EC2_TYPES
))

AMI_ID = TPL.add_parameter(Parameter(
    'ImageId',
    Type='AWS::EC2::Image::Id'
))

SUBNET_ID = TPL.add_parameter(Parameter(
    'SubnetId',
    Type='AWS::EC2::Subnet::Id'
))

INSTANCE_AZ = TPL.add_parameter(Parameter(
    'InstanceAz',
    Type='String'
))

KEY_PAIR = TPL.add_parameter(Parameter(
    'KeyPairName',
    Type='AWS::EC2::KeyPair::KeyName'
))

DISK_INIT_FAILURE_STOP = TPL.add_parameter(Parameter(
    'FailIfDiskInitFails',
    Type='String',
    AllowedValues=[
        'True',
        'False'
    ],
    Default='True'
))

KEY_CON = TPL.add_condition('KmsKeyCon', Equals(Ref(ENCRYPTION_KEY_ID), 'default'))
CACHE_DISKS_CON = TPL.add_condition('KmsKeyCon', Equals(Ref(USE_CACHE_DISK), 'True'))
DISK_FAILURE_CON = TPL.add_condition('DiskInitStopsCon', Equals(Ref(DISK_INIT_FAILURE_STOP), 'True'))


CACHE_DISKS = []

for count in range(3, 6):
    DISK = TPL.add_resource(Volume(
        f"CacheDisk{count-3}",
        Condition=CACHE_DISKS_CON,
        VolumeType=Ref(CACHE_DISK_TYPE),
        AvailabilityZone=Ref(INSTANCE_AZ),
        Size=Ref(CACHE_DISK_SIZE)
    ))
    CACHE_DISKS.append(DISK)


RAID_DISKS = []
for count in range(7, 16):
    DISK = TPL.add_resource(Volume(
        f"RaidDisk{count-7}",
        VolumeType=Ref(CACHE_DISK_TYPE),
        AvailabilityZone=Ref(INSTANCE_AZ),
        Size=Ref(RAID_DISK_SIZE)
    ))
    RAID_DISKS.append(DISK)


WH = TPL.add_resource(WaitConditionHandle(
    'ConditionHandle'
))

WC = TPL.add_resource(WaitCondition(
    'WaitCondition',
    Condition=DISK_FAILURE_CON,
    Handle=Ref(WH),
    Timeout=600
))

INSTANCE_TITLE = 'ComputeNode'
INSTANCE = TPL.add_resource(Instance(
    INSTANCE_TITLE,
    InstanceType=Ref(INSTANCE_TYPE),
    ImageId=Ref(AMI_ID),
    KeyName=Ref(KEY_PAIR),
    SubnetId=Ref(SUBNET_ID),
    Volumes=[
        MountPoint(
            Device=f"/dev/xvd{alpha[count+3]}",
            VolumeId=Ref(disk)
        ) for count, disk in enumerate(CACHE_DISKS + RAID_DISKS)
    ],
    UserData=Base64(Join('\n', [
        '#!/usr/bin/env bash',
        'export PATH=$PATH:/opt/aws/bin',
        'cfn-init -v || yum install aws-cfn-bootstrap -y',
        Sub(f"cfn-init --region ${{AWS::Region}} --resource {INSTANCE_TITLE} --stack ${{AWS::StackId}}"),
        'if [ $? -ne 0 ]; then',
        Sub(f"cfn-signal -e 1 -r 'Failed to initialize' '${{{WH.title}}}'"),
        'else',
        Sub(f"cfn-signal -e 0 '${{{WH.title}}}'"),
        'fi',
        '# EOF'
    ])),
    Metadata=cloudformation.Metadata(
        cloudformation.Init(
            cloudformation.InitConfigSets(
                default=[
                    'disksconfig',
                ]
            ),
            disksconfig=cloudformation.InitConfig(
                packages={
                    'yum': {
                        'parted': []
                    }
                },
                files={
                    '/etc/cache.disks.config': {
                        'owner': 'root',
                        'group': 'root',
                        'mode': '644',
                        'content': Join('\n', [
                            Sub(f"/dev/xvd{alpha[count+3]}=${{{disk.title}}}") for  count, disk in enumerate(CACHE_DISKS)
                        ])
                    },
                    '/etc/raid.disks.config': {
                        'owner': 'root',
                        'group': 'root',
                        'mode': '644',
                        'content': Join('\n', [
                            Sub(f"/dev/xvd{alpha[count+7]}=${{{disk.title}}}") for  count, disk in enumerate(RAID_DISKS)
                        ])
                    }
                }
            )
        )
    )
))

with open('raid_12disks.yml', 'w') as fd:
    fd.write(TPL.to_yaml())
