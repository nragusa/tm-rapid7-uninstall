# Overview

This script will accept a CSV file containing a list of EC2 instance IDs, check the validity of each ID, and then use AWS Systems Manager to remove a package that was previously installed with AWS Systems Manager Distributor.

## Usage

```bash
python uninstall.py -p <package> [-m <mode>] <path to csv>
```

The `-m` or `--mode` option is optional and can be set to either 'distributor' (default) or 'powershell'.

The script assumes a header in the file and that the first column contains the instance ID. For example:

```csv
resourceId, package
i-12345678910, MyPackage
i-21234567891, MyPackage
...
```

You may also need to specify the region to use. At the top of the script, set `REGION_NAME` appropriately.