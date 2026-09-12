SELECT
    vm.id,
    vm.name,
    vm.primary_ip,
    vm.agent_id,
    vm.current_inventory_id,
    a.name AS agent_name,
    a.current_inventory_id AS agent_inventory_id,
    i.hostname AS inventory_hostname,
    i.primary_ip AS inventory_ip
FROM virtual_machines vm
LEFT JOIN agents a
       ON a.id = vm.agent_id
LEFT JOIN inventory_snapshots i
       ON i.id = vm.current_inventory_id
WHERE vm.name = 'NUME_VM';


SELECT
    id,
    name,
    agent_uuid,
    current_inventory_id,
    last_contact_at,
    last_success_at
FROM agents
WHERE name = 'NUME_AGENT';
