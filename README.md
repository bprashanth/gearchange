Invocation via docker compose 
```
$ docker-compose down --rmi all --volumes --remove-orphans
$ docker-compose up -d --build
```
Backup the mongo in docker and run another local mongo against it 
```
$ docker inspect <container>
... inspect the output for the dbPath volume mount

$ scripts/backup_restore_mongo.sh --src_dir <output from docker inspect> --dst_dir ~/mongo/data/db/cc/...
```

Generate report (sudo seems necessary when working with a backup/restore from docker?) 
```
$ sudo mongod --dbpath ~/mongo/data/db/cc/gearchange/poller/backup/ --bind_ip 0.0.0.0 --port 27017
$ python3 report.py
$ python3 mongo_to_excel.py
```


## Appendix

### Bucket management 

This section contains details on the s3 bucket the excel sheets are uploaded to
Creation
```shell
$ aws s3api create-bucket --bucket climate-gearchange-2024 --region  ap-south-1 --create-bucket-configuration LocationConstraint=ap-south-1 
{
    "Location": "http://climate-gearchange-2024.s3.amazonaws.com/"
}
```
List 
```shell
$ aws s3 ls s3://climate-gearchange-2024/ --recursive 
```
Disable public access blocks 
```shell
$ aws s3api put-public-access-block --bucket climate-gearchange-2024 --public-access-block-configuration BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false
```
Allow world reading
```
$ aws s3api put-bucket-policy --bucket climate-gearchange-2024 --policy file://bucket-policy.json
```
Copying and accessing files 
```
$ aws s3 cp ~/Downloads/create_iam_policies.sh s3://climate-gearchange-2024/ 
$ curl https://climate-gearchange-2024.s3.ap-south-1.amazonaws.com/create_iam_policies.sh
```


### HTTPS (Cloudfront)


