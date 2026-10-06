SELECT
    source_id,
    vdom,
    policy_id,
    name,
    status,
    srcaddr_json,
    dstaddr_json
FROM fortigate_policies
WHERE policy_id = 517;


SELECT
    object_type,
    COUNT(*) AS nr,
    SUM(subnet <> '') AS cu_subnet,
    SUM(start_ip <> '') AS cu_start_ip,
    SUM(end_ip <> '') AS cu_end_ip
FROM fortigate_addresses
GROUP BY object_type
ORDER BY nr DESC;


SELECT
    COUNT(*) AS total_vm_ip
FROM (
    SELECT COALESCE(NULLIF(i.primary_ip,''), NULLIF(vm.primary_ip,''), '') AS ip
    FROM virtual_machines vm
    LEFT JOIN inventory_snapshots i ON i.id = vm.current_inventory_id
    WHERE vm.retired = 0
) x
WHERE ip <> '';
