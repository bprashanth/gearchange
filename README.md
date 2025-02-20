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

