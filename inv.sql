-- VM-DOC 0.21.73 - diagnostic inventory_snapshots (READ ONLY)
-- MariaDB: executati in baza VM-DOC. Nu modifica si nu sterge date.

-- 1. Volumul logic al snapshoturilor si efectul schimbarii la fiecare colectare.
SELECT COUNT(*) AS snapshots,
       COUNT(DISTINCT agent_id) AS agents,
       ROUND(COALESCE(SUM(payload_size),0)/1024/1024,2) AS total_payload_mib,
       ROUND(COALESCE(AVG(payload_size),0)/1024,2) AS average_payload_kib,
       SUM(changed_from_previous=0) AS marked_unchanged,
       MIN(received_at) AS oldest, MAX(received_at) AS newest
FROM inventory_snapshots;

-- 2. Dimensiunea tabelei alocata de InnoDB (estimari data_length/index_length).
SELECT table_name, engine, table_rows,
       ROUND(data_length/1024/1024,2) AS data_mib,
       ROUND(index_length/1024/1024,2) AS indexes_mib,
       ROUND(data_free/1024/1024,2) AS free_allocated_mib
FROM information_schema.tables
WHERE table_schema=DATABASE() AND table_name='inventory_snapshots';

-- 3. Top 20 agenti dupa volumul logic stocat.
SELECT i.agent_id, MAX(a.name) AS agent_name,
       COUNT(*) AS snapshots,
       ROUND(SUM(i.payload_size)/1024/1024,2) AS payload_mib,
       ROUND(AVG(i.payload_size)/1024,2) AS avg_snapshot_kib,
       MIN(i.received_at) AS oldest, MAX(i.received_at) AS newest
FROM inventory_snapshots AS i
LEFT JOIN agents AS a ON a.id=i.agent_id
GROUP BY i.agent_id
ORDER BY SUM(i.payload_size) DESC
LIMIT 20;

-- 4. Agenti care depasesc plafonul implicit de 30 snapshoturi.
SELECT agent_id, COUNT(*) AS snapshots,
       ROUND(SUM(payload_size)/1024/1024,2) AS payload_mib,
       MIN(received_at) AS oldest
FROM inventory_snapshots
GROUP BY agent_id
HAVING COUNT(*) > 30
ORDER BY COUNT(*) DESC, SUM(payload_size) DESC
LIMIT 30;

-- 5. Numarul snapshoturilor referite de evenimente in inventory_changes.
-- ATENTIE: FK inventory_changes.inventory_id -> inventory_snapshots.id este ON DELETE CASCADE.
SELECT COUNT(DISTINCT inventory_id) AS distinct_snapshots_referenced,
       COUNT(*) AS total_events
FROM inventory_changes;

-- 6. Snapshoturile referite de documentele generate.
SELECT COUNT(DISTINCT source_inventory_id) AS distinct_snapshots_referenced,
       COUNT(*) AS total_documents
FROM generated_documents;

-- 7. Evolutia stocarii pe zile (payload logic, nu dimensiune .ibd).
SELECT DATE(received_at) AS collection_day,
       COUNT(*) AS snapshots,
       ROUND(SUM(payload_size)/1024/1024,2) AS payload_mib
FROM inventory_snapshots
GROUP BY DATE(received_at)
ORDER BY collection_day DESC
LIMIT 45;
