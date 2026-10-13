mongo --host 127.0.0.1 --port 27017 --quiet \
  --eval '
    db.getMongo().setReadPref("secondaryPreferred");
    printjson(db.adminCommand({
      listDatabases: 1,
      nameOnly: true
    }));
  '
